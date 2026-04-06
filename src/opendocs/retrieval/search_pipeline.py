"""Five-stage hybrid search pipeline (ADR-0012).

Stage 1: QueryPreprocessor (normalize + sanitize)
Stage 2: Pre-filter (SQL WHERE → candidate doc_ids)
Stage 3: Dual retrieval (trigram FTS + HNSW dense)
Stage 4: Score fusion (normalize + weight + rank)
Stage 5: Evidence assembly (Citation per §8.4)
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from sqlalchemy.engine import Engine

from opendocs.config.settings import RetrievalSettings
from opendocs.indexing.hnsw_manager import HnswManager
from opendocs.retrieval.dense_searcher import DenseSearcher
from opendocs.retrieval.embedder import LocalNgramEmbedder
from opendocs.retrieval.evidence import (
    SearchResponse,
    SearchResult,
    build_citation,
)
from opendocs.retrieval.filters import SearchFilter, apply_pre_filter
from opendocs.retrieval.fts_searcher import FtsSearcher
from opendocs.retrieval.query_preprocessor import QueryPreprocessor
from opendocs.retrieval.rerank import (
    ScoreBreakdown,
    compute_freshness,
    fuse_scores,
    normalize_bm25,
    normalize_cosine,
)
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import ChunkRepository
from opendocs.utils.time import utcnow_naive


def _normalize_channel_scores(
    raw_scores: dict[str, float],
    normalizer: Callable[[list[float]], list[float]],
) -> dict[str, float]:
    """Normalize one score channel without depending on set iteration order."""
    if not raw_scores:
        return {}
    ordered_items = list(raw_scores.items())
    normalized = normalizer([score for _, score in ordered_items])
    return {
        chunk_id: normalized_score
        for (chunk_id, _), normalized_score in zip(ordered_items, normalized, strict=True)
    }


class SearchPipeline:
    """Orchestrate hybrid search across FTS5 and HNSW channels."""

    def __init__(
        self,
        engine: Engine,
        hnsw_manager: HnswManager,
        embedder: LocalNgramEmbedder,
        *,
        settings: RetrievalSettings | None = None,
    ) -> None:
        self._engine = engine
        self._hnsw = hnsw_manager
        self._embedder = embedder
        self._settings = settings or RetrievalSettings()
        self._preprocessor = QueryPreprocessor()
        self._fts = FtsSearcher(self._preprocessor)
        self._dense = DenseSearcher(hnsw_manager, embedder)

    def execute(
        self,
        query: str,
        *,
        filters: SearchFilter | None = None,
        top_k: int | None = None,
    ) -> SearchResponse:
        start = time.monotonic()
        k = top_k or self._settings.top_k
        trace_id = str(uuid.uuid4())
        candidate_limit = k * 3
        prepared_query = self._preprocessor.prepare(query)

        with session_scope(self._engine) as session:
            chunk_repo = ChunkRepository(session)
            # Stage 2: Pre-filter
            doc_ids = apply_pre_filter(session, filters)

            # Short-circuit: if filter is active but matches zero docs
            if doc_ids is not None and len(doc_ids) == 0:
                return SearchResponse(
                    query=query,
                    results=[],
                    total_candidates=0,
                    trace_id=trace_id,
                    duration_sec=time.monotonic() - start,
                    filters_applied=filters,
                )

            # Stage 3a: FTS5 trigram
            fts_results = self._fts.search_prepared(
                session,
                prepared_query,
                doc_ids=doc_ids,
                limit=candidate_limit,
            )

            # Stage 3b: Dense HNSW
            allowed_chunk_ids: set[str] | None = None
            if doc_ids is not None:
                allowed_chunk_ids = chunk_repo.list_chunk_ids_by_doc_ids(doc_ids)
                if not allowed_chunk_ids:
                    return SearchResponse(
                        query=query,
                        results=[],
                        total_candidates=0,
                        trace_id=trace_id,
                        duration_sec=time.monotonic() - start,
                        filters_applied=filters,
                    )

            dense_map: dict[str, float] = {}
            for variant in prepared_query.variants:
                if allowed_chunk_ids is None:
                    dense_results = self._dense.search(variant.text, k=candidate_limit)
                else:
                    dense_results = self._dense.search_filtered(
                        variant.text,
                        allowed_ids=allowed_chunk_ids,
                        k=candidate_limit,
                    )
                for chunk_id, distance in dense_results:
                    current = dense_map.get(chunk_id)
                    if current is None or distance < current:
                        dense_map[chunk_id] = distance

            # Stage 4: Score fusion
            # Collect all candidate chunk_ids
            fts_map: dict[str, tuple[str, float]] = {}
            for cid, did, score in fts_results:
                fts_map[cid] = (did, score)

            all_chunk_ids = set(fts_map.keys()) | set(dense_map.keys())
            if not all_chunk_ids:
                return SearchResponse(
                    query=query,
                    results=[],
                    total_candidates=0,
                    trace_id=trace_id,
                    duration_sec=time.monotonic() - start,
                    filters_applied=filters,
                )

            search_records = chunk_repo.load_search_records(all_chunk_ids)
            total_candidates = len(search_records)
            if total_candidates == 0:
                return SearchResponse(
                    query=query,
                    results=[],
                    total_candidates=0,
                    trace_id=trace_id,
                    duration_sec=time.monotonic() - start,
                    filters_applied=filters,
                )

            fts_norm_map = _normalize_channel_scores(
                {
                    chunk_id: score
                    for chunk_id, (_, score) in fts_map.items()
                    if chunk_id in search_records
                },
                normalize_bm25,
            )
            dense_norm_map = _normalize_channel_scores(
                {
                    chunk_id: distance
                    for chunk_id, distance in dense_map.items()
                    if chunk_id in search_records
                },
                normalize_cosine,
            )

            # Load chunk and document data for scoring + assembly
            now = utcnow_naive()

            scored: list[tuple[str, float, ScoreBreakdown]] = []
            for cid, record in search_records.items():
                lex_raw = fts_map[cid][1] if cid in fts_map else 0.0
                lex_norm = fts_norm_map.get(cid, 0.0)
                dense_raw = dense_map.get(cid, 2.0)  # max distance if missing
                dense_norm = dense_norm_map.get(cid, 0.0)

                fresh = compute_freshness(record.modified_at, now)
                hybrid = fuse_scores(lex_norm, dense_norm, fresh, self._settings)

                # Skip results with negligible relevance (both channels near zero)
                if lex_norm < 0.01 and dense_norm < 0.01:
                    continue

                breakdown = ScoreBreakdown(
                    lexical_raw=lex_raw,
                    lexical_normalized=lex_norm,
                    dense_raw=dense_raw,
                    dense_normalized=dense_norm,
                    freshness_boost=fresh,
                    hybrid_score=hybrid,
                )
                scored.append((cid, hybrid, breakdown))

            # Sort by hybrid score descending, take top_k
            scored.sort(key=lambda x: x[1], reverse=True)
            top = scored[:k]

            # Stage 5: Evidence assembly
            results: list[SearchResult] = []
            for cid, hybrid, breakdown in top:
                record = search_records.get(cid)
                if record is None:
                    continue

                citation = build_citation(
                    doc_id=record.doc_id,
                    chunk_id=cid,
                    path=record.display_path,
                    page_no=record.page_no,
                    paragraph_start=record.paragraph_start,
                    paragraph_end=record.paragraph_end,
                    char_start=record.char_start,
                    char_end=record.char_end,
                    text=record.text,
                    heading_path=record.heading_path,
                )

                summary = record.text[:200].replace("\n", " ").strip()
                if len(record.text) > 200:
                    summary += "..."

                results.append(
                    SearchResult(
                        chunk_id=cid,
                        doc_id=record.doc_id,
                        title=record.title,
                        path=record.display_path,
                        summary=summary,
                        modified_at=record.modified_at,
                        score=hybrid,
                        score_breakdown=breakdown,
                        citation=citation,
                    )
                )

        return SearchResponse(
            query=query,
            results=results,
            total_candidates=total_candidates,
            trace_id=trace_id,
            duration_sec=time.monotonic() - start,
            filters_applied=filters,
        )

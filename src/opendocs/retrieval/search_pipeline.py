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
from opendocs.storage.repositories import ChunkRepository, DocumentRepository
from opendocs.utils.time import utcnow_naive


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
                from sqlalchemy import text as sa_text

                placeholders = ", ".join(f":d{i}" for i in range(len(doc_ids)))
                params = {f"d{i}": d for i, d in enumerate(doc_ids)}
                rows = session.execute(
                    sa_text(f"SELECT chunk_id FROM chunks WHERE doc_id IN ({placeholders})"),
                    params,
                ).fetchall()
                allowed_chunk_ids = {r[0] for r in rows}

            dense_map: dict[str, float] = {}
            for variant in prepared_query.variants:
                dense_results = self._dense.search(
                    variant.text,
                    k=candidate_limit,
                    allowed_ids=allowed_chunk_ids,
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
            total_candidates = len(all_chunk_ids)

            if not all_chunk_ids:
                return SearchResponse(
                    query=query,
                    results=[],
                    total_candidates=0,
                    trace_id=trace_id,
                    duration_sec=time.monotonic() - start,
                    filters_applied=filters,
                )

            # Normalize FTS scores
            fts_scores = [fts_map[cid][1] for cid in all_chunk_ids if cid in fts_map]
            fts_normalized = normalize_bm25(fts_scores) if fts_scores else []
            fts_norm_map: dict[str, float] = {}
            fts_idx = 0
            for cid in all_chunk_ids:
                if cid in fts_map:
                    fts_norm_map[cid] = fts_normalized[fts_idx]
                    fts_idx += 1

            # Normalize dense scores
            dense_distances = [dense_map[cid] for cid in all_chunk_ids if cid in dense_map]
            dense_normalized = normalize_cosine(dense_distances) if dense_distances else []
            dense_norm_map: dict[str, float] = {}
            dense_idx = 0
            for cid in all_chunk_ids:
                if cid in dense_map:
                    dense_norm_map[cid] = dense_normalized[dense_idx]
                    dense_idx += 1

            # Load chunk and document data for scoring + assembly
            now = utcnow_naive()
            chunk_repo = ChunkRepository(session)
            doc_repo = DocumentRepository(session)

            scored: list[tuple[str, float, ScoreBreakdown]] = []
            for cid in all_chunk_ids:
                lex_raw = fts_map[cid][1] if cid in fts_map else 0.0
                lex_norm = fts_norm_map.get(cid, 0.0)
                dense_raw = dense_map.get(cid, 2.0)  # max distance if missing
                dense_norm = dense_norm_map.get(cid, 0.0)

                chunk = chunk_repo.get_by_id(cid)
                if chunk is None:
                    continue
                doc = doc_repo.get_by_id(chunk.doc_id)
                if doc is None or doc.is_deleted_from_fs:
                    continue

                fresh = compute_freshness(doc.modified_at, now)
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
                chunk = chunk_repo.get_by_id(cid)
                if chunk is None:
                    continue
                doc = doc_repo.get_by_id(chunk.doc_id)
                if doc is None:
                    continue

                citation = build_citation(
                    doc_id=doc.doc_id,
                    chunk_id=cid,
                    path=doc.relative_path,
                    page_no=chunk.page_no,
                    paragraph_start=chunk.paragraph_start,
                    paragraph_end=chunk.paragraph_end,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    text=chunk.text,
                    heading_path=chunk.heading_path,
                )

                summary = chunk.text[:200].replace("\n", " ").strip()
                if len(chunk.text) > 200:
                    summary += "..."

                results.append(
                    SearchResult(
                        chunk_id=cid,
                        doc_id=doc.doc_id,
                        title=doc.title,
                        path=doc.relative_path,
                        summary=summary,
                        modified_at=doc.modified_at,
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

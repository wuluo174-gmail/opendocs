"""Application-layer search service (spec §12 SearchService interface)."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.engine import Engine

from opendocs.app._audit_helpers import (
    build_text_input_audit_detail,
    create_audit_record,
    flush_audit_to_jsonl,
)
from opendocs.config.settings import RetrievalSettings
from opendocs.indexing.hnsw_manager import HnswManager
from opendocs.retrieval.embedder import LocalNgramEmbedder
from opendocs.retrieval.evidence import SearchResponse
from opendocs.retrieval.evidence_locator import EvidenceLocation, EvidenceLocator, EvidencePreview
from opendocs.retrieval.filters import SearchFilter
from opendocs.retrieval.search_pipeline import SearchPipeline
from opendocs.storage.db import session_scope

logger = logging.getLogger(__name__)


class SearchService:
    """Public search API — search, locate_evidence, open_document."""

    def __init__(
        self,
        engine: Engine,
        *,
        hnsw_path: Path,
        settings: RetrievalSettings | None = None,
    ) -> None:
        self._engine = engine
        embedder = LocalNgramEmbedder()
        hnsw = HnswManager(hnsw_path, dim=embedder.dim)
        # Repair dirty/mismatched HNSW on startup — critical for dense fallback
        hnsw.check_and_repair(engine, embedder=embedder)
        self._pipeline = SearchPipeline(engine, hnsw, embedder, settings=settings)
        self._locator = EvidenceLocator()

    def search(
        self,
        query: str,
        *,
        filters: SearchFilter | None = None,
        top_k: int | None = None,
    ) -> SearchResponse:
        """Execute a hybrid search query."""
        if not query or not query.strip():
            raise ValueError("query must not be empty")

        response = self._pipeline.execute(query, filters=filters, top_k=top_k)

        # Audit
        trace_id = response.trace_id
        try:
            with session_scope(self._engine) as session:
                audit = create_audit_record(
                    session,
                    actor="user",
                    operation="search_query",
                    target_type="search",
                    target_id=trace_id,
                    result="success",
                    detail_json=build_text_input_audit_detail(
                        query,
                        field_name="query",
                        result_count=len(response.results),
                        duration_sec=round(response.duration_sec, 3),
                        filters_applied=self._summarize_filters(filters),
                    ),
                    trace_id=trace_id,
                )
            if audit is not None:
                flush_audit_to_jsonl(audit)
        except Exception:
            logger.debug("Failed to write search audit", exc_info=True)

        return response

    def locate_evidence(self, doc_id: str, chunk_id: str) -> EvidenceLocation | None:
        """Locate a specific evidence item for citation display."""
        with session_scope(self._engine) as session:
            return self._locator.locate(session, doc_id, chunk_id)

    def load_evidence_preview(self, doc_id: str, chunk_id: str) -> EvidencePreview | None:
        """Resolve an in-app preview anchored to the selected citation."""
        with session_scope(self._engine) as session:
            return self._locator.build_preview(session, doc_id, chunk_id)

    def open_evidence(self, doc_id: str, chunk_id: str) -> bool:
        """Open a citation target without exposing absolute paths to search results."""
        with session_scope(self._engine) as session:
            target = self._locator.resolve_open_target(session, doc_id, chunk_id)
        if target is None:
            return False
        path, page_no, paragraph_range, char_range = target
        return self.open_document(
            path,
            page_no=page_no,
            paragraph_range=paragraph_range,
            char_range=char_range,
        )

    def reveal_evidence(self, doc_id: str, chunk_id: str) -> bool:
        """Reveal a citation target without exposing absolute paths to search results."""
        with session_scope(self._engine) as session:
            target = self._locator.resolve_open_target(session, doc_id, chunk_id)
        if target is None:
            return False
        path, _, _, _ = target
        return self.reveal_document(path)

    def open_document(
        self,
        path: str,
        *,
        page_no: int | None = None,
        paragraph_range: str | None = None,
        char_range: str | None = None,
    ) -> bool:
        """Open a document file with best-effort locator hints."""
        return EvidenceLocator.open_file(
            path,
            page_no=page_no,
            paragraph_range=paragraph_range,
            char_range=char_range,
        )

    def reveal_document(self, path: str) -> bool:
        """Reveal the document inside the platform file manager."""
        return EvidenceLocator.reveal_in_file_manager(path)

    @staticmethod
    def _summarize_filters(filters: SearchFilter | None) -> dict[str, object]:
        if filters is None:
            return {}
        summary: dict[str, object] = {}
        if filters.directory_prefixes:
            summary["directory_prefix_count"] = len(filters.directory_prefixes)
        if filters.source_root_ids:
            summary["source_root_count"] = len(filters.source_root_ids)
        if filters.categories:
            summary["category_count"] = len(filters.categories)
        if filters.tags:
            summary["tag_count"] = len(filters.tags)
        if filters.file_types:
            summary["file_type_count"] = len(filters.file_types)
        if filters.sensitivity_levels:
            summary["sensitivity_count"] = len(filters.sensitivity_levels)
        if filters.time_range is not None:
            summary["has_time_range"] = True
        return summary

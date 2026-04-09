"""Application-layer search service (spec §12 SearchService interface)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Iterable

from opendocs.app._audit_helpers import (
    build_text_input_audit_detail,
    create_audit_record,
    flush_audit_to_jsonl,
)
from opendocs.config.settings import RetrievalSettings
from opendocs.exceptions import RuntimeClosedError, SearchExecutionError
from opendocs.retrieval.evidence import SearchResponse
from opendocs.retrieval.evidence_locator import (
    EvidenceLocation,
    EvidenceLocator,
    EvidencePreview,
    ExternalActionResult,
)
from opendocs.retrieval.filters import SearchFilter
from opendocs.retrieval.search_pipeline import SearchPipeline
from opendocs.storage.db import session_scope

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from opendocs.app.runtime import OpenDocsRuntime


@dataclass(frozen=True)
class EvidenceActivation:
    """Resolved in-app preview plus optional external side-effect outcome."""

    preview: EvidencePreview | None
    external_action: ExternalActionResult | None = None


class SearchService:
    """Public search API — search, activate evidence, and open documents."""

    def __init__(
        self,
        runtime: OpenDocsRuntime,
        *,
        settings: RetrievalSettings | None = None,
    ) -> None:
        self._runtime = runtime
        self._engine = runtime.engine
        self._semantic_indexer = runtime.semantic_indexer
        self._settings = settings
        self._locator = EvidenceLocator()

    def _ensure_runtime_open(self) -> None:
        self._runtime.ensure_open()

    def search(
        self,
        query: str,
        *,
        filters: SearchFilter | None = None,
        top_k: int | None = None,
    ) -> SearchResponse:
        """Execute a hybrid search query."""
        self._ensure_runtime_open()
        if not query or not query.strip():
            raise ValueError("query must not be empty")

        failure_trace_id = str(uuid.uuid4())
        failure_detail = build_text_input_audit_detail(
            query,
            field_name="query",
            filters_applied=self._summarize_filters(filters),
        )

        try:
            response = self._build_pipeline().execute(query, filters=filters, top_k=top_k)
        except ValueError:
            raise
        except RuntimeClosedError:
            raise
        except Exception as exc:
            logger.exception(
                "Search execution failed for query_sha256=%s",
                failure_detail["query_sha256"],
            )
            self._write_search_audit(
                trace_id=failure_trace_id,
                query=query,
                filters=filters,
                result="failure",
                detail_overrides={
                    "error_type": type(exc).__name__,
                },
            )
            raise SearchExecutionError(
                "search backend failed; review local logs or rebuild the index",
                trace_id=failure_trace_id,
            ) from exc

        # Audit
        self._write_search_audit(
            trace_id=response.trace_id,
            query=query,
            filters=filters,
            result="success",
            detail_overrides={
                "total_candidates": response.total_candidates,
                "result_count": len(response.results),
                "duration_sec": round(response.duration_sec, 3),
            },
        )

        return response

    def _build_pipeline(self) -> SearchPipeline:
        """Resolve one fresh search backend from the committed dense artifact."""
        self._semantic_indexer.ensure_ready()
        hnsw, embedder = self._semantic_indexer.build_query_backend()
        return SearchPipeline(self._engine, hnsw, embedder, settings=self._settings)

    def locate_evidence(self, doc_id: str, chunk_id: str) -> EvidenceLocation | None:
        """Locate a specific evidence item for citation display."""
        self._ensure_runtime_open()
        with session_scope(self._engine) as session:
            return self._locator.locate(session, doc_id, chunk_id)

    def load_evidence_preview(self, doc_id: str, chunk_id: str) -> EvidencePreview | None:
        """Resolve an in-app preview anchored to the selected citation."""
        self._ensure_runtime_open()
        with session_scope(self._engine) as session:
            return self._locator.build_preview(session, doc_id, chunk_id)

    def load_evidence_previews(
        self,
        references: Iterable[tuple[str, str]],
    ) -> dict[tuple[str, str], EvidencePreview]:
        """Batch-load evidence previews for S5 QA/summary orchestration."""
        self._ensure_runtime_open()
        resolved: dict[tuple[str, str], EvidencePreview] = {}
        unique_refs = list(dict.fromkeys(references))
        if not unique_refs:
            return resolved

        with session_scope(self._engine) as session:
            for doc_id, chunk_id in unique_refs:
                preview = self._locator.build_preview(session, doc_id, chunk_id)
                if preview is not None:
                    resolved[(doc_id, chunk_id)] = preview
        return resolved

    def activate_evidence(
        self,
        doc_id: str,
        chunk_id: str,
        *,
        auto_open: bool = True,
    ) -> EvidenceActivation:
        """Load preview content and optionally attempt a real document jump."""
        self._ensure_runtime_open()
        preview = self.load_evidence_preview(doc_id, chunk_id)
        location = self.locate_evidence(doc_id, chunk_id)
        external_action = None
        if (
            auto_open
            and location is not None
            and location.can_open
            and location.external_jump_supported
        ):
            external_action = self.open_evidence(doc_id, chunk_id)
        return EvidenceActivation(
            preview=preview,
            external_action=external_action,
        )

    def open_evidence(self, doc_id: str, chunk_id: str) -> ExternalActionResult:
        """Open a citation target without exposing absolute paths to search results."""
        self._ensure_runtime_open()
        with session_scope(self._engine) as session:
            target = self._locator.resolve_open_target(session, doc_id, chunk_id)
        if target is None:
            return EvidenceLocator.unresolved_evidence_result("open")
        path, page_no, paragraph_range, char_range = target
        return self.open_document(
            path,
            page_no=page_no,
            paragraph_range=paragraph_range,
            char_range=char_range,
        )

    def reveal_evidence(self, doc_id: str, chunk_id: str) -> ExternalActionResult:
        """Reveal a citation target without exposing absolute paths to search results."""
        self._ensure_runtime_open()
        with session_scope(self._engine) as session:
            target = self._locator.resolve_open_target(session, doc_id, chunk_id)
        if target is None:
            return EvidenceLocator.unresolved_evidence_result("reveal")
        path, _, _, _ = target
        return self.reveal_document(path)

    def open_document(
        self,
        path: str,
        *,
        page_no: int | None = None,
        paragraph_range: str | None = None,
        char_range: str | None = None,
    ) -> ExternalActionResult:
        """Open a document file with best-effort locator hints."""
        self._ensure_runtime_open()
        return EvidenceLocator.open_file(
            path,
            page_no=page_no,
            paragraph_range=paragraph_range,
            char_range=char_range,
        )

    def reveal_document(self, path: str) -> ExternalActionResult:
        """Reveal the document inside the platform file manager."""
        self._ensure_runtime_open()
        return EvidenceLocator.reveal_in_file_manager(path)

    @staticmethod
    def _summarize_filters(filters: SearchFilter | None) -> dict[str, object]:
        if filters is None:
            return {}
        summary: dict[str, object] = {}
        if filters.source_roots:
            summary["source_root_count"] = len(filters.source_roots)
        if filters.directory_prefixes:
            summary["directory_prefix_count"] = len(filters.directory_prefixes)
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

    def _write_search_audit(
        self,
        *,
        trace_id: str,
        query: str,
        filters: SearchFilter | None,
        result: str,
        detail_overrides: dict[str, object] | None = None,
    ) -> None:
        detail = build_text_input_audit_detail(
            query,
            field_name="query",
            filters_applied=self._summarize_filters(filters),
        )
        if detail_overrides:
            detail.update(detail_overrides)

        try:
            with session_scope(self._engine) as session:
                audit = create_audit_record(
                    session,
                    actor="user",
                    operation="search_query",
                    target_type="search",
                    target_id=trace_id,
                    result=result,
                    detail_json=detail,
                    trace_id=trace_id,
                )
            if audit is not None:
                flush_audit_to_jsonl(audit)
        except Exception:
            logger.debug("Failed to write search audit", exc_info=True)

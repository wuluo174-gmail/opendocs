"""Application-layer summary service (spec §11.1 SummaryService)."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.engine import Engine

from opendocs.app._audit_helpers import (
    create_audit_record,
    flush_audit_to_jsonl,
)
from opendocs.app.search_service import SearchService
from opendocs.config.settings import RetrievalSettings
from opendocs.generation.markdown_exporter import export_markdown
from opendocs.generation.models import SummaryResponse
from opendocs.generation.summary_pipeline import SummaryPipeline
from opendocs.provider.mock import MockProvider
from opendocs.retrieval.filters import SearchFilter
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import ChunkRepository

logger = logging.getLogger(__name__)


class SummaryService:
    """Public summary API — summarize documents, export Markdown."""

    def __init__(
        self,
        engine: Engine,
        *,
        hnsw_path: Path,
        provider: MockProvider | None = None,
        retrieval_settings: RetrievalSettings | None = None,
    ) -> None:
        self._engine = engine
        self._search = SearchService(engine, hnsw_path=hnsw_path, settings=retrieval_settings)
        self._pipeline = SummaryPipeline(provider or MockProvider())

    def summarize(
        self,
        query: str,
        *,
        filters: SearchFilter | None = None,
        top_k: int = 20,
    ) -> SummaryResponse:
        """Summarize documents matching query."""
        search_response = self._search.search(query, filters=filters, top_k=top_k)

        chunk_texts: dict[str, str] = {}
        with session_scope(self._engine) as session:
            repo = ChunkRepository(session)
            for r in search_response.results:
                chunk = repo.get_by_id(r.chunk_id)
                if chunk is not None:
                    chunk_texts[r.chunk_id] = chunk.text

        response = self._pipeline.summarize(search_response.results, chunk_texts)
        self._audit(response)
        return response

    def export(self, response: SummaryResponse) -> str:
        """Export a SummaryResponse as Markdown."""
        return export_markdown(response)

    def _audit(self, response: SummaryResponse) -> None:
        try:
            with session_scope(self._engine) as session:
                audit = create_audit_record(
                    session,
                    actor="system",
                    operation="summary_generate",
                    target_type="generation",
                    target_id=response.trace_id,
                    result="success",
                    detail_json={
                        "source_doc_count": len(response.source_doc_ids),
                        "insight_count": len(response.insights),
                        "citation_count": len(response.citations),
                        "duration_sec": round(response.duration_sec, 3),
                    },
                    trace_id=response.trace_id,
                )
            if audit is not None:
                flush_audit_to_jsonl(audit)
        except Exception:
            logger.debug("Failed to write summary audit", exc_info=True)

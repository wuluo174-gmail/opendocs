"""Application-layer QA service (spec §11.1 QAService interface)."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from sqlalchemy.engine import Engine

from opendocs.app._audit_helpers import (
    build_text_input_audit_detail,
    create_audit_record,
    flush_audit_to_jsonl,
)
from opendocs.app.search_service import SearchService
from opendocs.config.settings import RetrievalSettings
from opendocs.provider.mock import MockProvider
from opendocs.qa.models import EvidencePackage, QAResponse
from opendocs.qa.qa_pipeline import QAPipeline
from opendocs.retrieval.filters import SearchFilter
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import ChunkRepository

logger = logging.getLogger(__name__)


class QAService:
    """Public QA API — ask questions, get cited answers."""

    def __init__(
        self,
        engine: Engine,
        *,
        hnsw_path: Path,
        provider: MockProvider | None = None,
        retrieval_settings: RetrievalSettings | None = None,
        min_evidence: int = 1,
        min_score: float = 0.15,
    ) -> None:
        self._engine = engine
        self._search = SearchService(engine, hnsw_path=hnsw_path, settings=retrieval_settings)
        self._pipeline = QAPipeline(
            provider or MockProvider(),
            min_evidence=min_evidence,
            min_score=min_score,
        )

    def ask(
        self,
        query: str,
        *,
        filters: SearchFilter | None = None,
        top_k: int = 12,
    ) -> QAResponse:
        """Answer a question using document evidence."""
        if not query or not query.strip():
            raise ValueError("query must not be empty")

        trace_id = str(uuid.uuid4())
        search_response = self._search.search(query, filters=filters, top_k=top_k)

        chunk_texts = self._load_chunk_texts(
            [r.chunk_id for r in search_response.results]
        )

        package = EvidencePackage(
            query=query,
            results=search_response.results,
            chunk_texts=chunk_texts,
            trace_id=trace_id,
        )

        response = self._pipeline.run(package)

        self._audit(query, response)

        return response

    def _load_chunk_texts(self, chunk_ids: list[str]) -> dict[str, str]:
        texts: dict[str, str] = {}
        with session_scope(self._engine) as session:
            repo = ChunkRepository(session)
            for cid in chunk_ids:
                chunk = repo.get_by_id(cid)
                if chunk is not None:
                    texts[cid] = chunk.text
        return texts

    def _audit(self, query: str, response: QAResponse) -> None:
        try:
            with session_scope(self._engine) as session:
                audit = create_audit_record(
                    session,
                    actor="system",
                    operation="qa_answer",
                    target_type="answer",
                    target_id=response.trace_id,
                    result="success",
                    detail_json=build_text_input_audit_detail(
                        query,
                        field_name="query",
                        status=response.status.value,
                        citation_count=len(response.citations),
                        duration_sec=round(response.duration_sec, 3),
                    ),
                    trace_id=response.trace_id,
                )
            if audit is not None:
                flush_audit_to_jsonl(audit)
        except Exception:
            logger.debug("Failed to write QA audit", exc_info=True)

"""Application-layer generation service (spec §11.1 GenerationService)."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from sqlalchemy.engine import Engine

from opendocs.app._audit_helpers import create_audit_record, flush_audit_to_jsonl
from opendocs.app.search_service import SearchService
from opendocs.config.settings import RetrievalSettings
from opendocs.generation.draft_pipeline import GenerationPipeline
from opendocs.generation.models import Draft
from opendocs.provider.mock import MockProvider
from opendocs.retrieval.filters import SearchFilter
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import ChunkRepository

logger = logging.getLogger(__name__)


class GenerationService:
    """Public generation API — generate drafts, edit, confirm save."""

    def __init__(
        self,
        engine: Engine,
        *,
        hnsw_path: Path,
        provider: MockProvider | None = None,
        retrieval_settings: RetrievalSettings | None = None,
        output_dir: str = "OpenDocs_Output",
    ) -> None:
        self._engine = engine
        self._search = SearchService(engine, hnsw_path=hnsw_path, settings=retrieval_settings)
        self._pipeline = GenerationPipeline(provider or MockProvider())
        self._output_dir = Path(output_dir)

    def list_templates(self) -> list[str]:
        return self._pipeline.list_templates()

    def generate(
        self,
        query: str,
        *,
        template_name: str | None = None,
        template_vars: dict[str, str] | None = None,
        free_form_instruction: str | None = None,
        filters: SearchFilter | None = None,
        top_k: int = 20,
    ) -> Draft:
        search_response = self._search.search(query, filters=filters, top_k=top_k)

        chunk_texts: dict[str, str] = {}
        with session_scope(self._engine) as session:
            repo = ChunkRepository(session)
            for r in search_response.results:
                chunk = repo.get_by_id(r.chunk_id)
                if chunk is not None:
                    chunk_texts[r.chunk_id] = chunk.text

        draft = self._pipeline.generate(
            search_response.results,
            chunk_texts,
            template_name=template_name,
            template_vars=template_vars,
            free_form_instruction=free_form_instruction,
        )

        self._audit_generate(draft)
        return draft

    def edit_draft(self, draft: Draft, new_content: str) -> Draft:
        if draft.saved:
            raise ValueError("cannot edit a saved draft")
        draft.content = new_content
        return draft

    def confirm_save(self, draft: Draft, *, output_dir: Path | None = None) -> Path:
        if draft.saved:
            raise ValueError("draft already saved")

        target_dir = output_dir or self._output_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        prefix = draft.template_name or "draft"
        filename = f"{prefix}_{draft.draft_id[:8]}.md"
        output_path = target_dir / filename

        output_path.write_text(draft.content, encoding="utf-8")
        draft.saved = True

        self._audit_save(draft, output_path)
        return output_path

    def _audit_generate(self, draft: Draft) -> None:
        try:
            with session_scope(self._engine) as session:
                audit = create_audit_record(
                    session,
                    actor="system",
                    operation="draft_generate",
                    target_type="generation",
                    target_id=draft.draft_id,
                    result="success",
                    detail_json={
                        "template_name": draft.template_name,
                        "source_doc_count": len(draft.source_doc_ids),
                        "citation_count": len(draft.citations),
                    },
                    trace_id=draft.trace_id,
                )
            if audit is not None:
                flush_audit_to_jsonl(audit)
        except Exception:
            logger.debug("Failed to write draft_generate audit", exc_info=True)

    def _audit_save(self, draft: Draft, output_path: Path) -> None:
        try:
            with session_scope(self._engine) as session:
                audit = create_audit_record(
                    session,
                    actor="system",
                    operation="draft_save",
                    target_type="generation",
                    target_id=draft.draft_id,
                    result="success",
                    detail_json={
                        "output_path": str(output_path.resolve()),
                        "template_name": draft.template_name,
                        "citation_count": len(draft.citations),
                        "content_sha256": hashlib.sha256(
                            draft.content.encode("utf-8")
                        ).hexdigest(),
                        "content_length": len(draft.content),
                    },
                    trace_id=draft.trace_id,
                )
            if audit is not None:
                flush_audit_to_jsonl(audit)
        except Exception:
            logger.debug("Failed to write draft_save audit", exc_info=True)

"""Draft generation pipeline — template or free-form with citations."""

from __future__ import annotations

import uuid
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from opendocs.generation.models import Draft
from opendocs.provider.base import GenerateRequest
from opendocs.provider.mock import MockProvider
from opendocs.retrieval.evidence import SearchResult
from opendocs.utils.time import utcnow_naive

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def build_evidence_prompt(
    results: list[SearchResult],
    chunk_texts: dict[str, str],
) -> str:
    parts = ["请根据以下文档内容生成文档：\n\n"]
    for r in results:
        text = chunk_texts.get(r.chunk_id, r.summary)
        parts.append(
            f"[EVIDENCE chunk_id={r.chunk_id}]\n"
            f"来源：{r.path}\n"
            f"{text}\n"
            f"[/EVIDENCE]\n\n"
        )
    return "".join(parts)


class GenerationPipeline:
    """Template or free-form generation with citation preservation."""

    def __init__(self, provider: MockProvider) -> None:
        self._provider = provider
        self._env = Environment(
            loader=FileSystemLoader(_TEMPLATE_DIR),
            autoescape=False,
            undefined=StrictUndefined,
        )

    def list_templates(self) -> list[str]:
        return sorted(
            p.stem for p in _TEMPLATE_DIR.glob("*.j2")
        )

    def generate(
        self,
        results: list[SearchResult],
        chunk_texts: dict[str, str],
        *,
        template_name: str | None = None,
        template_vars: dict[str, str] | None = None,
        free_form_instruction: str | None = None,
    ) -> Draft:
        if template_name:
            tpl = self._env.get_template(f"{template_name}.j2")
            system_prompt = tpl.render(**(template_vars or {}))
        elif free_form_instruction:
            system_prompt = free_form_instruction
        else:
            raise ValueError("must provide template_name or free_form_instruction")

        user_prompt = build_evidence_prompt(results, chunk_texts)
        response = self._provider.generate(
            GenerateRequest(system_prompt=system_prompt, user_prompt=user_prompt)
        )

        return Draft(
            draft_id=str(uuid.uuid4()),
            template_name=template_name,
            content=response.text,
            citations=[r.citation for r in results],
            source_doc_ids=list({r.doc_id for r in results}),
            trace_id=str(uuid.uuid4()),
            created_at=utcnow_naive(),
        )

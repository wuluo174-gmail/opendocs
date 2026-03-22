"""Summary pipeline — multi-document summarize via LLM."""

from __future__ import annotations

import time
import uuid

from opendocs.generation.insight_extractor import extract_insights
from opendocs.generation.models import SummaryResponse
from opendocs.provider.base import GenerateRequest
from opendocs.provider.mock import MockProvider
from opendocs.retrieval.evidence import Citation, SearchResult

_SUMMARY_SYSTEM = (
    "你是 OpenDocs 文档助手。根据提供的文档内容生成结构化摘要。\n"
    "输出格式：\n"
    "1. 概要总结\n"
    "2. 关键决策（用 [DECISION] 标记）\n"
    "3. 风险项（用 [RISK] 标记）\n"
    "4. 待办事项（用 [TODO] 标记）\n"
    "每个条目必须引用来源 [CIT:chunk_id]。"
)


class SummaryPipeline:
    """Summarize multiple documents with insight extraction."""

    def __init__(self, provider: MockProvider) -> None:
        self._provider = provider

    def summarize(
        self,
        results: list[SearchResult],
        chunk_texts: dict[str, str],
    ) -> SummaryResponse:
        t0 = time.monotonic()
        trace_id = str(uuid.uuid4())

        prompt = self._build_prompt(results, chunk_texts)
        response = self._provider.generate(
            GenerateRequest(system_prompt=_SUMMARY_SYSTEM, user_prompt=prompt)
        )

        doc_ids = list({r.doc_id for r in results})
        all_citations = [r.citation for r in results]
        insights = extract_insights(response.text, results, chunk_texts)

        return SummaryResponse(
            summary_text=response.text,
            insights=insights,
            source_doc_ids=doc_ids,
            citations=all_citations,
            trace_id=trace_id,
            duration_sec=time.monotonic() - t0,
        )

    @staticmethod
    def _build_prompt(
        results: list[SearchResult],
        chunk_texts: dict[str, str],
    ) -> str:
        parts = ["请对以下文档内容进行结构化摘要：\n\n"]
        for r in results:
            text = chunk_texts.get(r.chunk_id, r.summary)
            parts.append(
                f"[EVIDENCE chunk_id={r.chunk_id}]\n"
                f"来源：{r.path}\n"
                f"{text}\n"
                f"[/EVIDENCE]\n\n"
            )
        return "".join(parts)

"""Markdown preview/export for QA and summary outputs."""

from __future__ import annotations

from collections import defaultdict

from opendocs.qa.models import ExportPreview, InsightResult, QAResult, ResultPayload, SummaryResult


class MarkdownExporter:
    """Convert result payloads into a previewable Markdown artifact."""

    def preview(self, result: ResultPayload, *, title: str) -> ExportPreview:
        if isinstance(result, QAResult):
            markdown = self._render_qa(result, title=title)
            citations = result.citations
        elif isinstance(result, SummaryResult):
            markdown = self._render_summary(result, title=title)
            citations = result.citations
        elif isinstance(result, InsightResult):
            markdown = self._render_insights(result, title=title)
            citations = result.citations
        else:  # pragma: no cover - defensive branch
            raise TypeError(f"unsupported export payload: {type(result)!r}")
        return ExportPreview(
            trace_id=result.trace_id,
            title=title,
            markdown=markdown,
            citations=citations,
        )

    @staticmethod
    def _render_qa(result: QAResult, *, title: str) -> str:
        lines = [f"# {title}", "", result.answer, "", "## 引用"]
        if not result.citations:
            lines.append("- 无")
        else:
            for index, citation in enumerate(result.citations, start=1):
                lines.append(
                    f"{index}. `{citation.path}` @{citation.char_range} — {citation.quote_preview}"
                )
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _render_summary(result: SummaryResult, *, title: str) -> str:
        lines = [f"# {title}", "", "## 摘要", result.summary, "", "## 引用"]
        for index, citation in enumerate(result.citations, start=1):
            lines.append(
                f"{index}. `{citation.path}` @{citation.char_range} — {citation.quote_preview}"
            )
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _render_insights(result: InsightResult, *, title: str) -> str:
        grouped: dict[str, list[str]] = defaultdict(list)
        for item in result.items:
            citation = item.citations[0] if item.citations else None
            suffix = ""
            if citation is not None:
                suffix = f" (`{citation.path}` @{citation.char_range})"
            grouped[item.kind].append(f"- {item.text}{suffix}")

        lines = [f"# {title}", "", "## 概览", result.overview, ""]
        for heading, key in (("决策", "decision"), ("风险", "risk"), ("待办", "todo")):
            lines.append(f"## {heading}")
            lines.extend(grouped.get(key, ["- 无"]))
            lines.append("")
        return "\n".join(lines).strip() + "\n"

"""Markdown exporter — render SummaryResponse to Markdown with citations."""

from __future__ import annotations

from opendocs.generation.models import SummaryResponse


def export_markdown(response: SummaryResponse) -> str:
    """Render a SummaryResponse as a Markdown document."""
    parts = ["# 文档摘要\n\n"]
    parts.append(response.summary_text)
    parts.append("\n\n")

    by_type = {"decision": [], "risk": [], "todo": []}
    for item in response.insights:
        by_type.setdefault(item.insight_type, []).append(item)

    type_titles = {"decision": "关键决策", "risk": "风险项", "todo": "待办事项"}

    for itype, title in type_titles.items():
        items = by_type.get(itype, [])
        if not items:
            continue
        parts.append(f"## {title}\n\n")
        for i, item in enumerate(items, 1):
            parts.append(f"{i}. {item.text}")
            if item.citations:
                refs = ", ".join(
                    f"`{c.path}" + (f":p{c.page_no}" if c.page_no else "") + "`"
                    for c in item.citations
                )
                parts.append(f"  \n   来源：{refs}")
            parts.append("\n")
        parts.append("\n")

    if response.citations:
        parts.append("## 引用来源\n\n")
        seen = set()
        for c in response.citations:
            key = (c.doc_id, c.chunk_id)
            if key in seen:
                continue
            seen.add(key)
            loc = c.path
            if c.page_no is not None:
                loc += f" (第{c.page_no}页)"
            elif c.paragraph_range:
                loc += f" (段落{c.paragraph_range})"
            parts.append(f"- {loc}: {c.quote_preview}\n")

    return "".join(parts)

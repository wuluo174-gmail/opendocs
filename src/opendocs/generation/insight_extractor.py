"""Insight extractor — parse decisions, risks, todos from LLM output."""

from __future__ import annotations

import re

from opendocs.generation.models import InsightItem
from opendocs.retrieval.evidence import SearchResult

_INSIGHT_PATTERN = re.compile(
    r"\[(DECISION|RISK|TODO)\]\s*(.*?)(?=\[(?:DECISION|RISK|TODO)\]|\Z)",
    re.DOTALL,
)

_CIT_PATTERN = re.compile(r"\[CIT:([^\]]+)\]")

_TYPE_MAP = {
    "DECISION": "decision",
    "RISK": "risk",
    "TODO": "todo",
}


def extract_insights(
    text: str,
    results: list[SearchResult],
    chunk_texts: dict[str, str],
) -> list[InsightItem]:
    """Parse structured insight markers from LLM output."""
    citation_lookup = {r.chunk_id: r.citation for r in results}
    items: list[InsightItem] = []

    for m in _INSIGHT_PATTERN.finditer(text):
        tag = m.group(1)
        body = m.group(2).strip()
        cited_ids = _CIT_PATTERN.findall(body)
        citations = [citation_lookup[cid] for cid in cited_ids if cid in citation_lookup]

        items.append(
            InsightItem(
                insight_type=_TYPE_MAP[tag],
                text=re.sub(r"\[CIT:[^\]]+\]", "", body).strip(),
                citations=citations,
            )
        )

    return items

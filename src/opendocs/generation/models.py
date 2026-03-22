"""Generation data structures — InsightItem, SummaryResponse."""

from __future__ import annotations

from dataclasses import dataclass, field

from opendocs.retrieval.evidence import Citation


@dataclass(frozen=True)
class InsightItem:
    """A single extracted insight (decision, risk, or todo)."""

    insight_type: str  # "decision" | "risk" | "todo"
    text: str
    citations: list[Citation]


@dataclass(frozen=True)
class SummaryResponse:
    """Result of multi-document summarization."""

    summary_text: str
    insights: list[InsightItem]
    source_doc_ids: list[str]
    citations: list[Citation]
    trace_id: str
    duration_sec: float

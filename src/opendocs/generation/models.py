"""Generation data structures — InsightItem, SummaryResponse, Draft."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

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


@dataclass
class Draft:
    """Mutable document draft — editable before save confirmation."""

    draft_id: str
    template_name: str | None
    content: str
    citations: list[Citation]
    source_doc_ids: list[str]
    trace_id: str
    created_at: datetime
    saved: bool = False

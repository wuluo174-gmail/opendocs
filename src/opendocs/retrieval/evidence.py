"""Citation, SearchResult, and SearchResponse — per spec §8.4."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from opendocs.domain import CharRange, ParagraphRange
from opendocs.retrieval.filters import SearchFilter
from opendocs.retrieval.rerank import ScoreBreakdown


@dataclass(frozen=True)
class Citation:
    """Internal citation object per §8.4.

    char_range is in normalized-text offsets (best-effort, ADR-0010).
    """

    doc_id: str
    chunk_id: str
    path: str
    page_no: int | None
    paragraph_range: str | None
    char_range: str
    quote_preview: str


@dataclass(frozen=True)
class SearchResult:
    chunk_id: str
    doc_id: str
    title: str
    path: str
    summary: str
    modified_at: datetime
    score: float
    score_breakdown: ScoreBreakdown
    citation: Citation


@dataclass(frozen=True)
class SearchResponse:
    query: str
    results: list[SearchResult]
    total_candidates: int
    trace_id: str
    duration_sec: float
    filters_applied: SearchFilter | None


def build_citation(
    *,
    doc_id: str,
    chunk_id: str,
    path: str,
    page_no: int | None,
    paragraph_start: int | None,
    paragraph_end: int | None,
    char_start: int,
    char_end: int,
    text: str,
    heading_path: str | None,
) -> Citation:
    """Build a Citation from chunk + document metadata."""
    para_locator = ParagraphRange.from_storage(paragraph_start, paragraph_end)
    para_range = para_locator.to_display_range() if para_locator is not None else None
    char_range = CharRange(start=char_start, end=char_end).to_display_range()
    quote_preview = text[:120].replace("\n", " ").strip()
    if len(text) > 120:
        quote_preview += "..."

    return Citation(
        doc_id=doc_id,
        chunk_id=chunk_id,
        path=path,
        page_no=page_no,
        paragraph_range=para_range,
        char_range=char_range,
        quote_preview=quote_preview,
    )

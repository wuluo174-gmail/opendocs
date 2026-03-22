"""QA data structures — EvidencePackage, GateResult, QAResponse."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from opendocs.retrieval.evidence import Citation, SearchResult


class GateVerdict(str, Enum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    CONFLICT = "conflict"


class AnswerStatus(str, Enum):
    FACTUAL = "factual"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class EvidencePackage:
    """Assembled evidence for a single QA query."""

    query: str
    results: list[SearchResult]
    chunk_texts: dict[str, str]
    trace_id: str


@dataclass(frozen=True)
class GateResult:
    """Outcome of the evidence gate evaluation."""

    verdict: GateVerdict
    checked_sources: list[Citation]
    conflict_groups: list[list[Citation]] | None
    evidence_count: int
    min_score: float


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of citation validation on LLM output."""

    valid: bool
    cited_chunk_ids: list[str]
    invalid_chunk_ids: list[str]


@dataclass(frozen=True)
class QAResponse:
    """Final QA response returned to caller."""

    status: AnswerStatus
    answer_text: str
    citations: list[Citation]
    checked_sources: list[Citation]
    conflict_sources: list[list[Citation]] | None = None
    next_steps: list[str] | None = None
    trace_id: str = ""
    duration_sec: float = 0.0

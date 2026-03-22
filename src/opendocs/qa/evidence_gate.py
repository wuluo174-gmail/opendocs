"""Evidence gate — pure rule-based pre-LLM decision."""

from __future__ import annotations

from opendocs.qa.conflict_detector import detect_conflicts
from opendocs.qa.models import EvidencePackage, GateResult, GateVerdict


class EvidenceGate:
    """Evaluate whether evidence is sufficient, insufficient, or conflicting.

    Runs BEFORE LLM call. If insufficient, skip LLM entirely.
    """

    def __init__(self, *, min_evidence: int = 1, min_score: float = 0.15) -> None:
        self._min_evidence = min_evidence
        self._min_score = min_score

    def evaluate(self, package: EvidencePackage) -> GateResult:
        checked = [r.citation for r in package.results]
        qualifying = [r for r in package.results if r.score >= self._min_score]

        if len(qualifying) < self._min_evidence:
            return GateResult(
                verdict=GateVerdict.INSUFFICIENT,
                checked_sources=checked,
                conflict_groups=None,
                evidence_count=len(qualifying),
                min_score=self._min_score,
            )

        conflict_groups = detect_conflicts(qualifying, package.chunk_texts)
        if conflict_groups:
            return GateResult(
                verdict=GateVerdict.CONFLICT,
                checked_sources=checked,
                conflict_groups=conflict_groups,
                evidence_count=len(qualifying),
                min_score=self._min_score,
            )

        return GateResult(
            verdict=GateVerdict.SUFFICIENT,
            checked_sources=checked,
            conflict_groups=None,
            evidence_count=len(qualifying),
            min_score=self._min_score,
        )

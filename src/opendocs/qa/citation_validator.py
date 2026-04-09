"""Citation validation for extractive QA outputs."""

from __future__ import annotations

from dataclasses import dataclass

from opendocs.qa.generator import StatementCandidate
from opendocs.qa.models import dedupe_citations, extract_fact_records, normalize_text
from opendocs.retrieval.evidence import Citation


@dataclass(frozen=True)
class ValidationResult:
    statements: list[StatementCandidate]
    citations: list[Citation]
    rejected_statements: list[str]


class CitationValidator:
    """Ensure each factual statement is grounded in at least one evidence chunk."""

    def validate(self, statements: list[StatementCandidate]) -> ValidationResult:
        accepted: list[StatementCandidate] = []
        rejected: list[str] = []
        citations: list[Citation] = []

        for statement in statements:
            if self._supports_fact(statement):
                accepted.append(statement)
                citations.append(statement.evidence.citation)
            else:
                rejected.append(statement.text)

        return ValidationResult(
            statements=accepted,
            citations=dedupe_citations(citations),
            rejected_statements=rejected,
        )

    @staticmethod
    def _is_supported(statement: str, evidence_text: str) -> bool:
        normalized_statement = normalize_text(statement)
        normalized_evidence = normalize_text(evidence_text)
        if normalized_statement and normalized_statement in normalized_evidence:
            return True
        return False

    @staticmethod
    def _supports_fact(statement: StatementCandidate) -> bool:
        if statement.fact is None:
            return CitationValidator._is_supported(statement.text, statement.evidence.preview_text)

        evidence_facts = extract_fact_records(statement.evidence.preview_text)
        same_key_facts = [fact for fact in evidence_facts if fact.key == statement.fact.key]
        if not same_key_facts:
            return False
        return any(
            fact.normalized_value == statement.fact.normalized_value for fact in same_key_facts
        )

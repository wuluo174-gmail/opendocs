"""Local extractive generation boundary for S5."""

from __future__ import annotations

from dataclasses import dataclass

from opendocs.qa.models import (
    EvidenceBundle,
    EvidenceItem,
    FactRecord,
    evidence_matches_subject,
    extract_terms,
    sentence_matches_requested_fact,
)


@dataclass(frozen=True)
class StatementCandidate:
    text: str
    evidence: EvidenceItem
    match_score: float
    fact: FactRecord | None = None


@dataclass(frozen=True)
class AnswerDraft:
    statements: list[StatementCandidate]
    uncertainty_notes: list[str]


@dataclass(frozen=True)
class SummaryDraft:
    lines: list[StatementCandidate]


class LocalExtractiveGenerator:
    """Use local evidence snippets to build deterministic drafts."""

    def generate_answer(self, question: str, bundle: EvidenceBundle) -> AnswerDraft:
        question_terms = extract_terms(question)
        plan = bundle.query_plan
        requested_fact_keys = set(plan.requested_fact_keys)
        subject_terms = set(plan.subject_terms)
        candidates: list[StatementCandidate] = []
        for item in bundle.items:
            if not evidence_matches_subject(item, subject_terms):
                continue
            for unit in item.units:
                matched_fact = False
                for fact in unit.facts:
                    if requested_fact_keys and fact.key not in requested_fact_keys:
                        continue
                    overlap = self._score_fact(question_terms, fact)
                    if overlap <= 0.0 and not sentence_matches_requested_fact(
                        unit.text,
                        requested_fact_keys,
                    ):
                        continue
                    candidates.append(
                        StatementCandidate(
                            text=fact.line_text,
                            evidence=item,
                            match_score=overlap + item.score,
                            fact=fact,
                        )
                    )
                    matched_fact = True

                if matched_fact:
                    continue

                if requested_fact_keys and not sentence_matches_requested_fact(
                    unit.text,
                    requested_fact_keys,
                ):
                    continue

                overlap = self._score_text(question_terms, unit.text)
                if overlap <= 0.0:
                    continue
                candidates.append(
                    StatementCandidate(
                        text=unit.text,
                        evidence=item,
                        match_score=overlap + item.score,
                    )
                )

        ranked = self._rank_unique_candidates(candidates)
        uncertainty_notes: list[str] = []
        if len(ranked) > 1:
            uncertainty_notes.append("当前回答基于已检索片段，建议在引用面板继续核验原文。")
        return AnswerDraft(
            statements=ranked[:3],
            uncertainty_notes=uncertainty_notes,
        )

    def generate_summary(self, bundle: EvidenceBundle) -> SummaryDraft:
        candidates: list[StatementCandidate] = []
        for item in bundle.items:
            if not item.units:
                continue
            for unit in item.units[:2]:
                candidates.append(
                    StatementCandidate(
                        text=unit.text,
                        evidence=item,
                        match_score=item.score,
                    )
                )
        return SummaryDraft(lines=self._rank_unique_candidates(candidates)[:6])

    @staticmethod
    def _score_fact(question_terms: set[str], fact: FactRecord) -> float:
        return LocalExtractiveGenerator._score_text(question_terms, fact.line_text)

    @staticmethod
    def _score_text(question_terms: set[str], text: str) -> float:
        line_terms = extract_terms(text)
        overlap = len(question_terms & line_terms)
        if overlap > 0:
            return float(overlap)
        normalized = text.casefold()
        for term in question_terms:
            if term and term in normalized:
                return 0.5
        return 0.0

    @staticmethod
    def _rank_unique_candidates(
        candidates: list[StatementCandidate],
    ) -> list[StatementCandidate]:
        ranked = sorted(
            candidates,
            key=lambda candidate: candidate.match_score,
            reverse=True,
        )
        deduped: list[StatementCandidate] = []
        seen: set[str] = set()
        for candidate in ranked:
            normalized = candidate.text.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(candidate)
        return deduped

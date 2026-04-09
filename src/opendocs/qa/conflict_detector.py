"""Conflict detection for document-grounded answers."""

from __future__ import annotations

from dataclasses import dataclass

from opendocs.qa.models import (
    ConflictSource,
    EvidenceBundle,
    EvidenceItem,
    evidence_matches_subject,
)


@dataclass(frozen=True)
class _FactEntry:
    key_label: str
    value: str
    evidence: EvidenceItem


class ConflictDetector:
    """Detect same-key / different-value conflicts across evidence chunks."""

    def detect(self, question: str, bundle: EvidenceBundle) -> list[ConflictSource]:
        del question  # The normalized query plan already owns intent + requested slots.

        requested_fact_keys = set(bundle.query_plan.requested_fact_keys)
        if not requested_fact_keys:
            return []

        subject_terms = set(bundle.query_plan.subject_terms)
        grouped: dict[str, dict[str, _FactEntry]] = {}

        for item in bundle.items:
            if not evidence_matches_subject(item, subject_terms):
                continue
            for fact in item.facts:
                if fact.key not in requested_fact_keys:
                    continue
                grouped.setdefault(fact.key, {})
                grouped[fact.key].setdefault(
                    fact.normalized_value,
                    _FactEntry(
                        key_label=fact.raw_key,
                        value=fact.value,
                        evidence=item,
                    ),
                )

        for fact_key in bundle.query_plan.requested_fact_keys:
            entries = grouped.get(fact_key, {})
            if len(entries) < 2:
                continue
            sources: list[ConflictSource] = []
            for entry in entries.values():
                sources.append(
                    ConflictSource(
                        title=entry.evidence.title,
                        path=entry.evidence.path,
                        summary=f"{entry.key_label}：{entry.value}",
                        citation=entry.evidence.citation,
                    )
                )
            if len(sources) >= 2:
                return sources[:3]
        return []

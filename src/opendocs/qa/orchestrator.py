"""Query intent classification and evidence bundle assembly for S5."""

from __future__ import annotations

from opendocs.qa.models import (
    EvidenceBundle,
    EvidenceItem,
    QueryIntent,
    QueryPlan,
    extract_evidence_units,
    extract_fact_records,
    extract_requested_fact_keys,
    extract_requested_insight_kinds,
    extract_subject_terms,
    is_compare_request,
    is_enumeration_request,
    is_summary_request,
    is_timeline_request,
)
from opendocs.retrieval.evidence import SearchResponse
from opendocs.retrieval.evidence_locator import EvidencePreview


class QAOrchestrator:
    """Own query classification and evidence package construction."""

    def classify(self, question: str) -> QueryIntent:
        requested_fact_keys = extract_requested_fact_keys(question)
        requested_insight_kinds = extract_requested_insight_kinds(question)

        if is_compare_request(question):
            return "compare"
        if is_timeline_request(question):
            return "timeline"
        if requested_insight_kinds:
            return "summary"
        if requested_fact_keys:
            if is_enumeration_request(question):
                return "fact_list"
            return "fact"
        if is_summary_request(question):
            return "summary"
        return "fact"

    def build_plan(self, question: str) -> QueryPlan:
        return QueryPlan(
            question=question,
            intent=self.classify(question),
            subject_terms=tuple(sorted(extract_subject_terms(question))),
            requested_fact_keys=extract_requested_fact_keys(question),
            requested_insight_kinds=extract_requested_insight_kinds(question),
        )

    def build_bundle(
        self,
        *,
        question: str,
        response: SearchResponse,
        previews: dict[tuple[str, str], EvidencePreview],
    ) -> EvidenceBundle:
        plan = self.build_plan(question)
        items: list[EvidenceItem] = []
        for result in response.results:
            preview = previews.get((result.doc_id, result.chunk_id))
            preview_text = (
                preview.preview_text if preview is not None else result.citation.quote_preview
            )
            units = extract_evidence_units(preview_text)
            items.append(
                EvidenceItem(
                    doc_id=result.doc_id,
                    chunk_id=result.chunk_id,
                    title=result.title,
                    path=result.path,
                    score=result.score,
                    modified_at=result.modified_at,
                    summary=result.summary,
                    citation=result.citation,
                    preview_text=preview_text,
                    units=units,
                    facts=extract_fact_records(preview_text),
                )
            )
        return EvidenceBundle(
            query=question,
            query_plan=plan,
            trace_id=response.trace_id,
            items=items,
            total_candidates=response.total_candidates,
        )

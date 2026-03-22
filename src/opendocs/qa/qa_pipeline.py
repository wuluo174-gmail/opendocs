"""QA pipeline — orchestrates gate, generate, validate."""

from __future__ import annotations

import time

from opendocs.provider.base import GenerateRequest, LLMProvider
from opendocs.qa.citation_validator import CitationValidator, strip_invalid_citations
from opendocs.qa.evidence_gate import EvidenceGate
from opendocs.qa.models import AnswerStatus, EvidencePackage, GateVerdict, QAResponse
from opendocs.qa.prompts import (
    NEXT_STEPS_INSUFFICIENT,
    SYSTEM_PROMPT,
    build_conflict_prompt,
    build_factual_prompt,
    build_insufficient_text,
)


class QAPipeline:
    """Pure logic pipeline: gate → generate → validate.

    No DB access, no audit — that belongs in QAService.
    """

    def __init__(
        self,
        provider: LLMProvider,
        *,
        min_evidence: int = 1,
        min_score: float = 0.15,
    ) -> None:
        self._provider = provider
        self._gate = EvidenceGate(min_evidence=min_evidence, min_score=min_score)
        self._validator = CitationValidator()

    def run(self, package: EvidencePackage) -> QAResponse:
        t0 = time.monotonic()
        gate_result = self._gate.evaluate(package)

        if gate_result.verdict == GateVerdict.INSUFFICIENT:
            return QAResponse(
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                answer_text=build_insufficient_text(gate_result.checked_sources),
                citations=[],
                checked_sources=gate_result.checked_sources,
                next_steps=list(NEXT_STEPS_INSUFFICIENT),
                trace_id=package.trace_id,
                duration_sec=time.monotonic() - t0,
            )

        if gate_result.verdict == GateVerdict.CONFLICT:
            prompt = build_conflict_prompt(package, gate_result.conflict_groups)  # type: ignore[arg-type]
            response = self._provider.generate(
                GenerateRequest(system_prompt=SYSTEM_PROMPT, user_prompt=prompt)
            )
            conflict_citations = [c for group in gate_result.conflict_groups for c in group]  # type: ignore[union-attr]
            return QAResponse(
                status=AnswerStatus.CONFLICT,
                answer_text=response.text,
                citations=conflict_citations,
                checked_sources=gate_result.checked_sources,
                conflict_sources=gate_result.conflict_groups,
                trace_id=package.trace_id,
                duration_sec=time.monotonic() - t0,
            )

        # SUFFICIENT path
        prompt = build_factual_prompt(package)
        response = self._provider.generate(
            GenerateRequest(system_prompt=SYSTEM_PROMPT, user_prompt=prompt)
        )

        validation = self._validator.validate(response.text, package.chunk_texts)
        answer_text = response.text
        if validation.invalid_chunk_ids:
            answer_text = strip_invalid_citations(answer_text, validation.invalid_chunk_ids)

        cited_citations = [
            r.citation for r in package.results if r.chunk_id in validation.cited_chunk_ids
        ]

        return QAResponse(
            status=AnswerStatus.FACTUAL,
            answer_text=answer_text,
            citations=cited_citations,
            checked_sources=gate_result.checked_sources,
            trace_id=package.trace_id,
            duration_sec=time.monotonic() - t0,
        )

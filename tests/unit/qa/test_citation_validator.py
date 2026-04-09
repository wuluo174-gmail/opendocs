"""Unit coverage for strict fact-value citation validation."""

from __future__ import annotations

from datetime import datetime

from opendocs.qa.citation_validator import CitationValidator
from opendocs.qa.generator import StatementCandidate
from opendocs.qa.models import EvidenceItem, FactRecord
from opendocs.retrieval.evidence import Citation


def test_citation_validator_rejects_same_key_different_value() -> None:
    validator = CitationValidator()
    evidence = EvidenceItem(
        doc_id="doc-1",
        chunk_id="chunk-1",
        title="Atlas 发布计划 V2",
        path="projects/atlas/release_plan_v2.md",
        score=0.9,
        modified_at=datetime(2026, 4, 1, 12, 0, 0),
        summary="Atlas 发布时间：2026-04-01",
        citation=Citation(
            doc_id="doc-1",
            chunk_id="chunk-1",
            path="projects/atlas/release_plan_v2.md",
            page_no=None,
            paragraph_range="1-1",
            char_range="0-20",
            quote_preview="Atlas 发布时间：2026-04-01",
        ),
        preview_text="Atlas 发布时间：2026-04-01",
        facts=(
            FactRecord(
                key="publish_time",
                raw_key="Atlas 发布时间",
                value="2026-04-01",
                normalized_value="2026-04-01",
                line_text="Atlas 发布时间：2026-04-01",
            ),
        ),
    )
    statement = StatementCandidate(
        text="Atlas 发布时间：2026-03-15",
        evidence=evidence,
        match_score=1.0,
        fact=FactRecord(
            key="publish_time",
            raw_key="Atlas 发布时间",
            value="2026-03-15",
            normalized_value="2026-03-15",
            line_text="Atlas 发布时间：2026-03-15",
        ),
    )

    result = validator.validate([statement])

    assert not result.statements
    assert result.rejected_statements == ["Atlas 发布时间：2026-03-15"]

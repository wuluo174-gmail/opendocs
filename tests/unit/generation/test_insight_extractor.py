"""Unit tests for InsightExtractor."""

from datetime import datetime

from opendocs.generation.insight_extractor import extract_insights
from opendocs.retrieval.evidence import Citation, SearchResult
from opendocs.retrieval.rerank import ScoreBreakdown


def _sr(chunk_id: str) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        doc_id="d1",
        title="test",
        path="/test.md",
        summary="text",
        modified_at=datetime(2026, 1, 1),
        score=0.5,
        score_breakdown=ScoreBreakdown(lexical_raw=-1.0, lexical_normalized=0.5, dense_raw=0.5, dense_normalized=0.5, freshness_boost=1.0, hybrid_score=0.5),
        citation=Citation(
            doc_id="d1",
            chunk_id=chunk_id,
            path="/test.md",
            page_no=None,
            paragraph_range=None,
            char_range="0-100",
            quote_preview="text",
        ),
    )


def test_extract_decision():
    text = "[DECISION] 决定采用方案A [CIT:c1]"
    items = extract_insights(text, [_sr("c1")], {"c1": "text"})
    assert len(items) == 1
    assert items[0].insight_type == "decision"
    assert "方案A" in items[0].text
    assert len(items[0].citations) == 1


def test_extract_multiple_types():
    text = (
        "[DECISION] 选择供应商X [CIT:c1]"
        "[RISK] 供货延迟风险 [CIT:c2]"
        "[TODO] 签订合同 [CIT:c1]"
    )
    items = extract_insights(text, [_sr("c1"), _sr("c2")], {"c1": "t", "c2": "t"})
    types = {i.insight_type for i in items}
    assert types == {"decision", "risk", "todo"}


def test_extract_no_markers():
    text = "普通文本没有标记"
    items = extract_insights(text, [_sr("c1")], {"c1": "text"})
    assert len(items) == 0

"""Unit tests for SummaryPipeline."""

from datetime import datetime

from opendocs.generation.summary_pipeline import SummaryPipeline
from opendocs.provider.mock import MockProvider
from opendocs.retrieval.evidence import Citation, SearchResult
from opendocs.retrieval.rerank import ScoreBreakdown


def _sr(chunk_id: str, doc_id: str, text: str) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        doc_id=doc_id,
        title="test",
        path="/test.md",
        summary=text,
        modified_at=datetime(2026, 1, 1),
        score=0.5,
        score_breakdown=ScoreBreakdown(lexical_raw=-1.0, lexical_normalized=0.5, dense_raw=0.5, dense_normalized=0.5, freshness_boost=1.0, hybrid_score=0.5),
        citation=Citation(
            doc_id=doc_id,
            chunk_id=chunk_id,
            path="/test.md",
            page_no=None,
            paragraph_range=None,
            char_range="0-100",
            quote_preview=text[:60],
        ),
    )


def test_summary_returns_response():
    pipeline = SummaryPipeline(MockProvider())
    r1 = _sr("c1", "d1", "项目进展顺利")
    r2 = _sr("c2", "d2", "团队人员充足")
    texts = {"c1": "项目进展顺利", "c2": "团队人员充足"}
    response = pipeline.summarize([r1, r2], texts)
    assert response.summary_text
    assert len(response.source_doc_ids) == 2
    assert len(response.citations) == 2
    assert response.trace_id
    assert response.duration_sec >= 0


def test_summary_single_doc():
    pipeline = SummaryPipeline(MockProvider())
    r = _sr("c1", "d1", "内容A")
    response = pipeline.summarize([r], {"c1": "内容A"})
    assert len(response.source_doc_ids) == 1

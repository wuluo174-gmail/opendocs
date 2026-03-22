"""Unit tests for QAPipeline with MockProvider."""

from datetime import datetime

from opendocs.provider.mock import MockProvider
from opendocs.qa.models import AnswerStatus, EvidencePackage
from opendocs.qa.qa_pipeline import QAPipeline
from opendocs.retrieval.evidence import Citation, SearchResult
from opendocs.retrieval.rerank import ScoreBreakdown


def _sr(chunk_id: str, doc_id: str, text: str, score: float = 0.5) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        doc_id=doc_id,
        title="test",
        path="/test.md",
        summary=text,
        modified_at=datetime(2026, 1, 1),
        score=score,
        score_breakdown=ScoreBreakdown(lexical_raw=-1.0, lexical_normalized=score, dense_raw=score, dense_normalized=score, freshness_boost=1.0, hybrid_score=score),
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


def test_factual_answer_has_citations():
    pipeline = QAPipeline(MockProvider(), min_evidence=1, min_score=0.1)
    r = _sr("c1", "d1", "项目预算为100万元")
    pkg = EvidencePackage(
        query="项目预算是多少",
        results=[r],
        chunk_texts={"c1": "项目预算为100万元"},
        trace_id="t1",
    )
    response = pipeline.run(pkg)
    assert response.status == AnswerStatus.FACTUAL
    assert len(response.citations) > 0
    assert response.trace_id == "t1"


def test_insufficient_evidence():
    pipeline = QAPipeline(MockProvider(), min_evidence=1, min_score=0.5)
    r = _sr("c1", "d1", "无关内容", score=0.1)
    pkg = EvidencePackage(
        query="不存在的问题",
        results=[r],
        chunk_texts={"c1": "无关内容"},
        trace_id="t2",
    )
    response = pipeline.run(pkg)
    assert response.status == AnswerStatus.INSUFFICIENT_EVIDENCE
    assert len(response.citations) == 0
    assert response.next_steps is not None
    assert len(response.next_steps) > 0


def test_insufficient_no_results():
    pipeline = QAPipeline(MockProvider(), min_evidence=1, min_score=0.1)
    pkg = EvidencePackage(
        query="不存在的问题",
        results=[],
        chunk_texts={},
        trace_id="t3",
    )
    response = pipeline.run(pkg)
    assert response.status == AnswerStatus.INSUFFICIENT_EVIDENCE


def test_conflict_detected():
    pipeline = QAPipeline(MockProvider(), min_evidence=1, min_score=0.1)
    r1 = _sr("c1", "d1", "预算100万")
    r2 = _sr("c2", "d2", "预算200万")
    pkg = EvidencePackage(
        query="预算多少",
        results=[r1, r2],
        chunk_texts={"c1": "预算100万", "c2": "预算200万"},
        trace_id="t4",
    )
    response = pipeline.run(pkg)
    assert response.status == AnswerStatus.CONFLICT
    assert response.conflict_sources is not None
    assert len(response.conflict_sources) >= 1

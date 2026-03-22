"""Unit tests for conflict detection."""

from datetime import datetime

from opendocs.qa.conflict_detector import detect_conflicts
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


def test_numeric_conflict():
    r1 = _sr("c1", "d1", "预算100万")
    r2 = _sr("c2", "d2", "预算200万")
    texts = {"c1": "预算100万", "c2": "预算200万"}
    conflicts = detect_conflicts([r1, r2], texts)
    assert conflicts is not None
    assert len(conflicts) >= 1


def test_negation_conflict():
    r1 = _sr("c1", "d1", "项目已完成验收")
    r2 = _sr("c2", "d2", "项目未完成验收")
    texts = {"c1": "项目已完成验收", "c2": "项目未完成验收"}
    conflicts = detect_conflicts([r1, r2], texts)
    assert conflicts is not None


def test_no_conflict_same_doc():
    r1 = _sr("c1", "d1", "预算100万")
    r2 = _sr("c2", "d1", "预算200万")
    texts = {"c1": "预算100万", "c2": "预算200万"}
    conflicts = detect_conflicts([r1, r2], texts)
    assert conflicts is None


def test_no_conflict_compatible():
    r1 = _sr("c1", "d1", "项目进展顺利")
    r2 = _sr("c2", "d2", "团队工作正常")
    texts = {"c1": "项目进展顺利", "c2": "团队工作正常"}
    conflicts = detect_conflicts([r1, r2], texts)
    assert conflicts is None


def test_single_doc_no_conflict():
    r1 = _sr("c1", "d1", "fact A")
    texts = {"c1": "fact A"}
    conflicts = detect_conflicts([r1], texts)
    assert conflicts is None

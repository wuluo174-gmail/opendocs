"""Unit tests for EvidenceGate."""

from datetime import datetime

from opendocs.qa.evidence_gate import EvidenceGate
from opendocs.qa.models import EvidencePackage, GateVerdict
from opendocs.retrieval.evidence import Citation, SearchResult
from opendocs.retrieval.rerank import ScoreBreakdown


def _make_result(
    chunk_id: str = "c1",
    doc_id: str = "d1",
    score: float = 0.5,
    text: str = "some text",
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        doc_id=doc_id,
        title="test",
        path="/test.md",
        summary=text,
        modified_at=datetime(2026, 1, 1),
        score=score,
        score_breakdown=ScoreBreakdown(
            lexical_raw=-1.0, lexical_normalized=score, dense_raw=score, dense_normalized=score, freshness_boost=1.0, hybrid_score=score
        ),
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


def _make_package(results: list[SearchResult], texts: dict[str, str] | None = None) -> EvidencePackage:
    chunk_texts = texts or {r.chunk_id: r.summary for r in results}
    return EvidencePackage(
        query="test query",
        results=results,
        chunk_texts=chunk_texts,
        trace_id="trace-1",
    )


def test_sufficient_with_good_score():
    gate = EvidenceGate(min_evidence=1, min_score=0.2)
    pkg = _make_package([_make_result(score=0.5)])
    result = gate.evaluate(pkg)
    assert result.verdict == GateVerdict.SUFFICIENT
    assert result.evidence_count == 1


def test_insufficient_no_results():
    gate = EvidenceGate(min_evidence=1, min_score=0.2)
    pkg = _make_package([])
    result = gate.evaluate(pkg)
    assert result.verdict == GateVerdict.INSUFFICIENT
    assert result.evidence_count == 0


def test_insufficient_low_score():
    gate = EvidenceGate(min_evidence=1, min_score=0.5)
    pkg = _make_package([_make_result(score=0.1)])
    result = gate.evaluate(pkg)
    assert result.verdict == GateVerdict.INSUFFICIENT


def test_conflict_detected():
    gate = EvidenceGate(min_evidence=1, min_score=0.1)
    r1 = _make_result(chunk_id="c1", doc_id="d1", score=0.5, text="预算100万")
    r2 = _make_result(chunk_id="c2", doc_id="d2", score=0.5, text="预算200万")
    pkg = _make_package([r1, r2])
    result = gate.evaluate(pkg)
    assert result.verdict == GateVerdict.CONFLICT
    assert result.conflict_groups is not None
    assert len(result.conflict_groups) >= 1


def test_no_conflict_same_doc():
    gate = EvidenceGate(min_evidence=1, min_score=0.1)
    r1 = _make_result(chunk_id="c1", doc_id="d1", score=0.5, text="预算100万")
    r2 = _make_result(chunk_id="c2", doc_id="d1", score=0.5, text="预算200万")
    pkg = _make_package([r1, r2])
    result = gate.evaluate(pkg)
    # same doc_id -> no cross-doc conflict
    assert result.verdict == GateVerdict.SUFFICIENT

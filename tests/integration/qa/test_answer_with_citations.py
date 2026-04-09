"""S5 TC-006 answer-with-citations coverage."""

from __future__ import annotations

from opendocs.app.qa_service import QAService
from opendocs.app.search_service import SearchService


def test_single_document_fact_answer_defaults_to_citations(
    qa_service: QAService,
    qa_search_service: SearchService,
) -> None:
    result = qa_service.answer("Atlas 项目负责人是谁？")

    assert result.result_type == "answered"
    assert result.citations
    assert "结论：" in result.answer
    assert "依据：" in result.answer
    assert any("王敏" in line for line in result.answer.splitlines())

    for citation in result.citations:
        location = qa_search_service.locate_evidence(citation.doc_id, citation.chunk_id)
        assert location is not None
        assert location.quote_preview


def test_cross_document_fact_answer_keeps_citations(
    qa_service: QAService,
) -> None:
    result = qa_service.answer("Atlas 项目当前有哪些关键决策？")

    assert result.result_type == "answered"
    assert len(result.citations) >= 1
    assert "来源：" in result.answer
    assert "决策" in result.answer


def test_enumerated_fact_question_routes_to_fact_list_path(
    qa_service: QAService,
) -> None:
    result = qa_service.answer("Atlas 有哪些发布时间？")

    assert result.result_type == "answered"
    assert len(result.citations) == 2
    assert "Atlas 发布时间：2026-03-15" in result.answer
    assert "Atlas 发布时间：2026-04-01" in result.answer
    assert "Atlas 月报" not in result.answer


def test_compare_question_routes_to_compare_path(
    qa_service: QAService,
) -> None:
    result = qa_service.answer("比较 Atlas 发布时间的版本差异")

    assert result.result_type == "answered"
    assert len(result.citations) >= 2
    assert "Atlas 发布计划 V1" in result.answer
    assert "Atlas 发布计划 V2" in result.answer
    assert "2026-03-15" in result.answer
    assert "2026-04-01" in result.answer


def test_timeline_question_routes_to_timeline_path(
    qa_service: QAService,
) -> None:
    result = qa_service.answer("Atlas 发布时间时间线是什么？")

    assert result.result_type == "answered"
    assert len(result.citations) >= 2
    assert "2026-03-15" in result.answer
    assert "2026-04-01" in result.answer
    assert result.answer.index("2026-03-15") < result.answer.index("2026-04-01")


def test_natural_sentence_fact_answer_is_grounded(
    qa_service: QAService,
) -> None:
    result = qa_service.answer("Aurora 项目负责人是谁？")

    assert result.result_type == "answered"
    assert result.citations
    assert "赵宁" in result.answer
    assert "Aurora 简报" in result.answer

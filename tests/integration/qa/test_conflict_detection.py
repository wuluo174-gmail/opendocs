"""S5 TC-008 conflict-detection coverage."""

from __future__ import annotations

from opendocs.app.qa_service import QAService


def test_conflict_answer_surfaces_two_sources(qa_service: QAService) -> None:
    result = qa_service.answer("Atlas 发布时间是什么？")

    assert result.result_type == "conflict"
    assert len(result.conflict_sources) >= 2
    assert len(result.citations) >= 2
    assert "冲突来源 A：" in result.answer
    assert "冲突来源 B：" in result.answer
    assert "暂不输出单一结论" in result.answer
    assert any("2026-03-15" in source.summary for source in result.conflict_sources)
    assert any("2026-04-01" in source.summary for source in result.conflict_sources)

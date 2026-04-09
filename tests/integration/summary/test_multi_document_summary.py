"""S5 TC-009 summary and insight export coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from opendocs.app.qa_service import QAService


def test_multi_document_summary_and_insights_are_traceable(
    qa_service: QAService,
    atlas_summary_doc_ids: list[str],
) -> None:
    summary = qa_service.summarize(doc_ids=atlas_summary_doc_ids)
    insights = qa_service.extract_insights(doc_ids=atlas_summary_doc_ids)

    assert summary.result_type == "summary"
    assert summary.citations
    assert "- " in summary.summary

    assert insights.result_type == "insights"
    assert insights.citations
    assert any(item.kind == "decision" for item in insights.items)
    assert any(item.kind == "risk" for item in insights.items)
    assert any(item.kind == "todo" for item in insights.items)
    assert all(item.citations for item in insights.items)


def test_markdown_export_requires_confirmation_and_writes_file(
    qa_service: QAService,
    atlas_summary_doc_ids: list[str],
    tmp_path: Path,
) -> None:
    insights = qa_service.extract_insights(doc_ids=atlas_summary_doc_ids)
    preview = qa_service.preview_markdown_export(insights, title="Atlas 洞察导出")

    assert "# Atlas 洞察导出" in preview.markdown
    assert "## 决策" in preview.markdown

    with pytest.raises(ValueError):
        qa_service.save_markdown_export(
            preview,
            tmp_path / "atlas_insights.md",
            confirmed=False,
        )

    exported = qa_service.save_markdown_export(
        preview,
        tmp_path / "atlas_insights.md",
        confirmed=True,
    )

    assert exported.exists()
    assert "## 风险" in exported.read_text(encoding="utf-8")


def test_natural_sentence_insights_are_extracted(
    qa_service: QAService,
    aurora_doc_ids: list[str],
) -> None:
    insights = qa_service.extract_insights(doc_ids=aurora_doc_ids)

    assert insights.result_type == "insights"
    assert any(item.kind == "decision" for item in insights.items)
    assert any(item.kind == "risk" for item in insights.items)
    assert any(item.kind == "todo" for item in insights.items)
    assert any("五月开始试点" in item.text for item in insights.items if item.kind == "decision")

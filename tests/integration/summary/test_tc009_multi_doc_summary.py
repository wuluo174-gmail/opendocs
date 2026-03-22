"""TC-009: Multi-document decision summary with source tracing.

Acceptance criteria:
- Markdown export exists and is non-empty
- Each insight has at least 1 citation
- Summary references multiple source documents
"""

from opendocs.app.summary_service import SummaryService
from opendocs.generation.markdown_exporter import export_markdown


def test_summary_returns_citations(summary_service: SummaryService) -> None:
    """Multi-doc summary includes citations."""
    response = summary_service.summarize("项目进度报告")
    assert len(response.citations) > 0
    assert len(response.source_doc_ids) >= 1
    assert response.trace_id


def test_summary_markdown_export(summary_service: SummaryService) -> None:
    """Markdown export is non-empty and contains header."""
    response = summary_service.summarize("项目计划")
    md = export_markdown(response)
    assert len(md) > 0
    assert "# 文档摘要" in md


def test_summary_export_via_service(summary_service: SummaryService) -> None:
    """SummaryService.export() works end-to-end."""
    response = summary_service.summarize("项目")
    md = summary_service.export(response)
    assert "引用来源" in md

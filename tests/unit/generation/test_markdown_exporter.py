"""Unit tests for Markdown exporter."""

from opendocs.generation.markdown_exporter import export_markdown
from opendocs.generation.models import InsightItem, SummaryResponse
from opendocs.retrieval.evidence import Citation


def _cit(chunk_id: str = "c1") -> Citation:
    return Citation(
        doc_id="d1",
        chunk_id=chunk_id,
        path="/test.md",
        page_no=1,
        paragraph_range="1-2",
        char_range="0-100",
        quote_preview="test content",
    )


def test_export_has_header():
    resp = SummaryResponse(
        summary_text="概要内容",
        insights=[],
        source_doc_ids=["d1"],
        citations=[_cit()],
        trace_id="t1",
        duration_sec=1.0,
    )
    md = export_markdown(resp)
    assert "# 文档摘要" in md
    assert "概要内容" in md


def test_export_with_insights():
    resp = SummaryResponse(
        summary_text="摘要",
        insights=[
            InsightItem(insight_type="decision", text="选择方案A", citations=[_cit()]),
            InsightItem(insight_type="risk", text="可能延期", citations=[_cit("c2")]),
        ],
        source_doc_ids=["d1"],
        citations=[_cit()],
        trace_id="t1",
        duration_sec=1.0,
    )
    md = export_markdown(resp)
    assert "关键决策" in md
    assert "选择方案A" in md
    assert "风险项" in md
    assert "可能延期" in md


def test_export_citation_section():
    resp = SummaryResponse(
        summary_text="摘要",
        insights=[],
        source_doc_ids=["d1"],
        citations=[_cit()],
        trace_id="t1",
        duration_sec=1.0,
    )
    md = export_markdown(resp)
    assert "引用来源" in md
    assert "/test.md" in md

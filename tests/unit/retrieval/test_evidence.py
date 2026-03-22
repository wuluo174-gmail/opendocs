"""Unit tests for Citation building and EvidenceLocator."""

from opendocs.domain import CharRange, ParagraphRange
from opendocs.retrieval.evidence import build_citation


class TestLocatorValueObjects:
    def test_paragraph_range_display_is_one_based(self) -> None:
        locator = ParagraphRange.from_storage(0, 2)
        assert locator is not None
        assert locator.to_display_range() == "1-3"

    def test_char_range_round_trip(self) -> None:
        locator = CharRange(start=12, end=48)
        assert locator.to_display_range() == "12-48"
        assert CharRange.parse("12-48") == locator


class TestBuildCitation:
    def test_pdf_with_page(self) -> None:
        cit = build_citation(
            doc_id="d1",
            chunk_id="c1",
            path="reports/report.pdf",
            page_no=3,
            paragraph_start=None,
            paragraph_end=None,
            char_start=100,
            char_end=500,
            text="This is test content for a PDF page.",
            heading_path=None,
        )
        assert cit.page_no == 3
        assert cit.path == "reports/report.pdf"
        assert cit.paragraph_range is None
        assert cit.char_range == "100-500"
        assert "test content" in cit.quote_preview

    def test_markdown_with_paragraphs(self) -> None:
        cit = build_citation(
            doc_id="d2",
            chunk_id="c2",
            path="notes/meeting.md",
            page_no=None,
            paragraph_start=5,
            paragraph_end=7,
            char_start=200,
            char_end=800,
            text="Meeting notes content here.",
            heading_path="Notes > Meeting",
        )
        assert cit.page_no is None
        assert cit.paragraph_range == "6-8"
        assert cit.char_range == "200-800"

    def test_single_paragraph(self) -> None:
        cit = build_citation(
            doc_id="d3",
            chunk_id="c3",
            path="plain/file.txt",
            page_no=None,
            paragraph_start=3,
            paragraph_end=3,
            char_start=0,
            char_end=100,
            text="Short text.",
            heading_path=None,
        )
        assert cit.paragraph_range == "4"

    def test_quote_preview_truncation(self) -> None:
        long_text = "A" * 200
        cit = build_citation(
            doc_id="d4",
            chunk_id="c4",
            path="plain/long.txt",
            page_no=None,
            paragraph_start=None,
            paragraph_end=None,
            char_start=0,
            char_end=200,
            text=long_text,
            heading_path=None,
        )
        assert len(cit.quote_preview) <= 123 + 3  # 120 + "..."
        assert cit.quote_preview.endswith("...")

    def test_cjk_content(self) -> None:
        cit = build_citation(
            doc_id="d5",
            chunk_id="c5",
            path="projects/zh_plan.md",
            page_no=None,
            paragraph_start=0,
            paragraph_end=2,
            char_start=0,
            char_end=50,
            text="项目计划书——本项目的目标是开发文档管理工具。",
            heading_path=None,
        )
        assert "项目计划" in cit.quote_preview
        assert cit.paragraph_range == "1-3"

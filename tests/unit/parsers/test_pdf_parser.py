"""Tests for PdfParser."""

from __future__ import annotations

from pathlib import Path

import pytest

from opendocs.parsers.pdf_parser import PdfParser  # noqa: E402


class TestPdfParser:
    def setup_method(self) -> None:
        self.parser = PdfParser()

    def test_supported_extensions(self) -> None:
        assert self.parser.supported_extensions() == [".pdf"]

    def test_parse_normal(self, tmp_pdf: Path) -> None:
        result = self.parser.parse(tmp_pdf)
        assert result.parse_status == "success"
        assert result.file_type == "pdf"
        assert result.page_count is not None
        assert result.page_count >= 1
        assert len(result.paragraphs) >= 1

    def test_page_no_preserved(self, tmp_pdf: Path) -> None:
        result = self.parser.parse(tmp_pdf)
        for para in result.paragraphs:
            assert para.page_no is not None
            assert para.page_no >= 1

    def test_char_offsets(self, tmp_pdf: Path) -> None:
        result = self.parser.parse(tmp_pdf)
        for para in result.paragraphs:
            assert para.start_char >= 0
            assert para.end_char >= para.start_char
            extracted = result.raw_text[para.start_char : para.end_char]
            assert extracted == para.text

    def test_chinese_pdf(self, tmp_pdf_chinese: Path) -> None:
        result = self.parser.parse(tmp_pdf_chinese)
        assert result.parse_status == "success"
        assert result.page_count >= 1

    def test_empty_pdf(self, tmp_pdf_empty: Path) -> None:
        result = self.parser.parse(tmp_pdf_empty)
        assert result.parse_status == "failed"
        assert result.paragraphs == []
        assert result.error is not None
        assert result.error.code == "no_text_layer"
        assert result.error_info == "no extractable text layer"

    def test_title_from_text(self, tmp_pdf: Path) -> None:
        result = self.parser.parse(tmp_pdf)
        # Should have a title (either from metadata or first line)
        assert result.title is not None

    def test_corrupted_pdf(self, tmp_path: Path) -> None:
        """A corrupted PDF should raise ParseFailedError."""
        from opendocs.exceptions import ParseFailedError

        p = tmp_path / "bad.pdf"
        p.write_bytes(b"not a pdf")
        with pytest.raises(ParseFailedError):
            self.parser.parse(p)

    def test_chinese_char_offsets(self, tmp_pdf_chinese: Path) -> None:
        """Chinese paragraphs should have accurate char offsets."""
        result = self.parser.parse(tmp_pdf_chinese)
        if not result.paragraphs:
            pytest.skip("CJK rendering may not produce text in all environments")
        for para in result.paragraphs:
            assert para.start_char >= 0
            assert para.end_char > para.start_char
            # Offset should match position in raw_text
            assert result.raw_text[para.start_char : para.end_char] == para.text

    def test_toc_heading_path(self, tmp_pdf_with_toc: Path) -> None:
        """PDF with TOC bookmarks should produce heading_path on paragraphs."""
        result = self.parser.parse(tmp_pdf_with_toc)
        assert result.parse_status == "success"
        assert result.page_count == 3
        paths = [p.heading_path for p in result.paragraphs if p.heading_path]
        # At least some paragraphs should have heading paths derived from TOC
        assert len(paths) > 0
        assert any("Chapter 1" in hp for hp in paths)
        assert any("Chapter 2" in hp for hp in paths)

    def test_toc_heading_hierarchy(self, tmp_pdf_with_toc: Path) -> None:
        """Section 2.1 heading_path should include parent Chapter 2."""
        result = self.parser.parse(tmp_pdf_with_toc)
        page3_paras = [p for p in result.paragraphs if p.page_no == 3]
        assert len(page3_paras) > 0
        for p in page3_paras:
            if p.heading_path:
                assert "Chapter 2" in p.heading_path
                assert "Section 2.1" in p.heading_path

    def test_multipage_page_no_varies(self, tmp_pdf_multipage: Path) -> None:
        """Multi-page PDF paragraphs should have different page numbers."""
        result = self.parser.parse(tmp_pdf_multipage)
        assert result.parse_status == "success"
        page_nos = {p.page_no for p in result.paragraphs if p.page_no}
        assert len(page_nos) >= 2, "Expected paragraphs from multiple pages"

    def test_toc_same_page_preserves_document_order(self, tmp_path: Path) -> None:
        """TOC entries on the same page must preserve original document order,
        not be re-sorted by level (issue #2 from audit)."""
        fitz_mod = pytest.importorskip("fitz")
        doc = fitz_mod.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Content on single page.")
        # TOC: H1 Ch1, H2 Sec1.1, H1 Ch2 — all on page 1
        doc.set_toc(
            [
                [1, "Ch1", 1],
                [2, "Sec1.1", 1],
                [1, "Ch2", 1],
            ]
        )
        pdf_path = tmp_path / "same_page_toc.pdf"
        doc.save(str(pdf_path))
        doc.close()

        result = self.parser.parse(pdf_path)
        # After processing all 3 TOC entries on page 1, the last entry is
        # H1 Ch2 which pops everything ≥ level 1.  So page_heading[1]
        # should end with "Ch2", NOT "Ch1 > Sec1.1".
        page1_paras = [p for p in result.paragraphs if p.page_no == 1]
        assert len(page1_paras) > 0
        hp = page1_paras[0].heading_path
        assert hp is not None
        assert hp == "Ch2", f"Expected 'Ch2' but got '{hp}'"

    def test_partial_status_when_some_pages_fail(self, tmp_path: Path) -> None:
        """S2-T04: PDF with some unreadable pages should yield partial status."""
        from unittest.mock import patch

        fitz = pytest.importorskip("fitz")
        doc = fitz.open()
        p1 = doc.new_page()
        p1.insert_text((72, 72), "Good page one content.")
        p2 = doc.new_page()
        p2.insert_text((72, 72), "Good page two content.")
        pdf_path = tmp_path / "partial.pdf"
        doc.save(str(pdf_path))
        doc.close()

        original_try_fitz = __import__(
            "opendocs.parsers.pdf_parser", fromlist=["_try_fitz"]
        )._try_fitz

        def fitz_with_page_failure(file_path: Path):
            extraction = original_try_fitz(file_path)
            # Simulate one page failing by removing it and recording failure
            if len(extraction.pages) >= 2:
                extraction.pages.pop()
                extraction.failed_pages.append(2)
            return extraction

        with patch("opendocs.parsers.pdf_parser._try_fitz", side_effect=fitz_with_page_failure):
            result = self.parser.parse(pdf_path)

        assert result.parse_status == "partial"
        assert result.error_info is not None
        assert "2" in result.error_info
        assert result.error is not None
        assert result.error.code == "partial_parse"
        assert result.error.details["failed_pages"] == [2]
        # Successfully parsed pages should still produce paragraphs
        assert len(result.paragraphs) >= 1
        # Offsets must remain valid
        for para in result.paragraphs:
            assert result.raw_text[para.start_char : para.end_char] == para.text

    def test_mixed_text_and_empty_page_is_partial(self, tmp_path: Path) -> None:
        """A document with some textual pages and some empty pages is partial."""
        from unittest.mock import patch

        from opendocs.parsers.pdf_parser import _PdfExtraction

        fake_extraction = _PdfExtraction(
            pages=[(1, "Page one text."), (2, "")],
            title=None,
            page_count=2,
            failed_pages=[],
            toc=[],
            empty_pages=[2],
        )

        fake_pdf = tmp_path / "mixed.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4\n")

        with patch("opendocs.parsers.pdf_parser._try_fitz", return_value=fake_extraction):
            result = self.parser.parse(fake_pdf)

        assert result.parse_status == "partial"
        assert result.error is not None
        assert result.error.code == "partial_parse"
        assert result.error.details["failed_pages"] == []
        assert result.error.details["empty_pages"] == [2]
        assert "no text extracted on pages: [2]" in result.error_info
        assert [para.page_no for para in result.paragraphs] == [1]

    def test_fallback_to_pypdf_is_marked_partial_and_auditable(self, tmp_path: Path) -> None:
        """S2-T01/T04: backend fallback must surface as a partial parse."""
        from unittest.mock import patch

        from opendocs.parsers.pdf_parser import _PdfExtraction

        fake_extraction = _PdfExtraction(
            pages=[(1, "Fallback title\n\nBody text.")],
            title=None,
            page_count=1,
            failed_pages=[],
            toc=[],
        )
        fake_pdf = tmp_path / "fallback.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4\n")

        with patch("opendocs.parsers.pdf_parser._try_fitz", side_effect=RuntimeError("fitz boom")):
            with patch("opendocs.parsers.pdf_parser._try_pypdf", return_value=fake_extraction):
                result = self.parser.parse(fake_pdf)

        assert result.parse_status == "partial"
        assert result.error_info is not None
        assert "fell back to pypdf" in result.error_info
        assert result.error is not None
        assert result.error.code == "partial_parse"
        assert result.error.details["failed_backend"] == "PyMuPDF"
        assert result.error.details["fallback_backend"] == "pypdf"
        assert result.error.details["degraded_fields"] == ["heading_path"]
        assert result.title == "Fallback title"

"""Tests for PdfParser."""

from __future__ import annotations

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

from opendocs.parsers.pdf_parser import PdfParser


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

    def test_chinese_pdf(self, tmp_pdf_chinese: Path) -> None:
        result = self.parser.parse(tmp_pdf_chinese)
        assert result.parse_status == "success"
        assert result.page_count >= 1

    def test_empty_pdf(self, tmp_pdf_empty: Path) -> None:
        result = self.parser.parse(tmp_pdf_empty)
        assert result.parse_status == "success"
        assert result.paragraphs == []

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

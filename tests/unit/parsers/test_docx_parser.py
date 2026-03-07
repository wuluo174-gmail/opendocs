"""Tests for DocxParser."""

from __future__ import annotations

from pathlib import Path

import pytest

docx = pytest.importorskip("docx")

from opendocs.parsers.docx_parser import DocxParser


class TestDocxParser:
    def setup_method(self) -> None:
        self.parser = DocxParser()

    def test_supported_extensions(self) -> None:
        assert self.parser.supported_extensions() == [".docx"]

    def test_parse_normal(self, tmp_docx: Path) -> None:
        result = self.parser.parse(tmp_docx)
        assert result.parse_status == "success"
        assert result.file_type == "docx"
        assert result.title == "Docx Title"
        assert len(result.paragraphs) >= 2

    def test_heading_extraction(self, tmp_docx: Path) -> None:
        result = self.parser.parse(tmp_docx)
        paths = [p.heading_path for p in result.paragraphs if p.heading_path]
        assert any("Heading One" in hp for hp in paths)
        assert any("Heading Two" in hp for hp in paths)

    def test_heading_hierarchy(self, tmp_docx: Path) -> None:
        result = self.parser.parse(tmp_docx)
        # Find paragraphs under Heading Two
        h2_paras = [
            p for p in result.paragraphs
            if p.heading_path and "Heading Two" in p.heading_path
        ]
        assert len(h2_paras) > 0
        # Heading Two (level 2) should be nested under Heading One (level 1)
        for p in h2_paras:
            assert "Heading One" in p.heading_path

    def test_char_offsets(self, tmp_docx: Path) -> None:
        result = self.parser.parse(tmp_docx)
        for para in result.paragraphs:
            assert para.start_char >= 0
            assert para.end_char >= para.start_char

    def test_chinese_content(self, tmp_docx_chinese: Path) -> None:
        result = self.parser.parse(tmp_docx_chinese)
        assert result.parse_status == "success"
        assert any("标题一" in p.text for p in result.paragraphs)
        assert any("第一段" in p.text for p in result.paragraphs)

    def test_empty_docx(self, tmp_docx_empty: Path) -> None:
        result = self.parser.parse(tmp_docx_empty)
        assert result.parse_status == "success"
        # Empty docx may still have some default paragraphs
        # but all should be empty-text filtered

    def test_corrupted_file(self, tmp_path: Path) -> None:
        """A corrupted .docx should raise ParseFailedError."""
        from opendocs.exceptions import ParseFailedError

        p = tmp_path / "bad.docx"
        p.write_bytes(b"this is not a docx")
        with pytest.raises(ParseFailedError):
            self.parser.parse(p)

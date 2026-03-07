"""Tests for TxtParser."""

from __future__ import annotations

from pathlib import Path

from opendocs.parsers.txt_parser import TxtParser


class TestTxtParser:
    def setup_method(self) -> None:
        self.parser = TxtParser()

    def test_supported_extensions(self) -> None:
        assert self.parser.supported_extensions() == [".txt"]

    def test_parse_normal(self, tmp_txt: Path) -> None:
        result = self.parser.parse(tmp_txt)
        assert result.parse_status == "success"
        assert result.file_type == "txt"
        assert result.title == "Title Line"
        assert len(result.paragraphs) == 3  # Title Line, First, Second
        assert result.paragraphs[0].text == "Title Line"
        assert result.paragraphs[1].text == "First paragraph."
        assert result.paragraphs[2].text == "Second paragraph."

    def test_char_offsets(self, tmp_txt: Path) -> None:
        result = self.parser.parse(tmp_txt)
        for para in result.paragraphs:
            # The paragraph text should be found at the indicated offsets
            assert para.start_char >= 0
            assert para.end_char > para.start_char

    def test_chinese_content(self, tmp_txt_chinese: Path) -> None:
        result = self.parser.parse(tmp_txt_chinese)
        assert result.parse_status == "success"
        assert result.title == "标题行"
        assert any("第一段" in p.text for p in result.paragraphs)

    def test_empty_file(self, tmp_txt_empty: Path) -> None:
        result = self.parser.parse(tmp_txt_empty)
        assert result.parse_status == "success"
        assert result.paragraphs == []
        assert result.title is None

    def test_page_no_is_none(self, tmp_txt: Path) -> None:
        result = self.parser.parse(tmp_txt)
        for para in result.paragraphs:
            assert para.page_no is None

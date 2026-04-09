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

    def test_char_offsets_exact(self, tmp_txt: Path) -> None:
        result = self.parser.parse(tmp_txt)
        for para in result.paragraphs:
            assert para.start_char >= 0
            assert para.end_char > para.start_char
            extracted = result.raw_text[para.start_char : para.end_char]
            assert extracted == para.text, (
                f"Offset mismatch: raw_text[{para.start_char}:{para.end_char}]="
                f"'{extracted}' != '{para.text}'"
            )

    def test_chinese_content(self, tmp_txt_chinese: Path) -> None:
        result = self.parser.parse(tmp_txt_chinese)
        assert result.parse_status == "success"
        assert result.title == "标题行"
        assert any("第一段" in p.text for p in result.paragraphs)

    def test_empty_file(self, tmp_txt_empty: Path) -> None:
        result = self.parser.parse(tmp_txt_empty)
        assert result.parse_status == "failed"
        assert result.paragraphs == []
        assert result.title is None
        assert result.error is not None
        assert result.error.code == "no_extractable_text"

    def test_page_no_is_none(self, tmp_txt: Path) -> None:
        result = self.parser.parse(tmp_txt)
        for para in result.paragraphs:
            assert para.page_no is None

    def test_chinese_char_offsets_exact(self, tmp_txt_chinese: Path) -> None:
        """Chinese paragraphs must have exact char offsets in raw_text."""
        result = self.parser.parse(tmp_txt_chinese)
        for para in result.paragraphs:
            extracted = result.raw_text[para.start_char : para.end_char]
            assert extracted == para.text, (
                f"Offset mismatch: raw_text[{para.start_char}:{para.end_char}]="
                f"'{extracted}' != '{para.text}'"
            )

    def test_duplicate_paragraphs(self, tmp_path: Path) -> None:
        """Repeated identical paragraphs must get distinct, correct offsets."""
        p = tmp_path / "dup.txt"
        p.write_text("Same text.\n\nSame text.\n\nSame text.", encoding="utf-8")
        result = self.parser.parse(p)
        assert len(result.paragraphs) == 3
        for para in result.paragraphs:
            assert result.raw_text[para.start_char : para.end_char] == para.text

    def test_gbk_encoded_file(self, tmp_path: Path) -> None:
        """GBK-encoded Chinese file must be parsed correctly, not garbled."""
        p = tmp_path / "gbk.txt"
        content = "标题行\n\n第一段中文内容。\n\n第二段中文内容。"
        p.write_bytes(content.encode("gbk"))
        result = self.parser.parse(p)
        assert result.parse_status == "success"
        assert "标题行" in result.raw_text
        assert "第一段" in result.raw_text
        assert "\ufffd" not in result.raw_text  # no replacement chars

    def test_gb2312_encoded_file(self, tmp_path: Path) -> None:
        """GB2312-encoded file should also be detected."""
        p = tmp_path / "gb2312.txt"
        content = "测试文件\n\n这是GB2312编码。"
        p.write_bytes(content.encode("gb2312"))
        result = self.parser.parse(p)
        assert result.parse_status == "success"
        assert "测试文件" in result.raw_text

    def test_whitespace_only_file_is_failed(self, tmp_path: Path) -> None:
        p = tmp_path / "blank.txt"
        p.write_text(" \n\t \n", encoding="utf-8")

        result = self.parser.parse(p)

        assert result.parse_status == "failed"
        assert result.paragraphs == []
        assert result.error is not None
        assert result.error.code == "no_extractable_text"

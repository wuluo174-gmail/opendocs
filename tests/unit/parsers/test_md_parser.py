"""Tests for MdParser."""

from __future__ import annotations

from pathlib import Path

from opendocs.parsers.md_parser import MdParser


class TestMdParser:
    def setup_method(self) -> None:
        self.parser = MdParser()

    def test_supported_extensions(self) -> None:
        assert self.parser.supported_extensions() == [".md"]

    def test_parse_normal(self, tmp_md: Path) -> None:
        result = self.parser.parse(tmp_md)
        assert result.parse_status == "success"
        assert result.file_type == "md"
        assert result.title == "Main Title"
        assert len(result.paragraphs) > 0

    def test_heading_path(self, tmp_md: Path) -> None:
        result = self.parser.parse(tmp_md)
        paths = [p.heading_path for p in result.paragraphs if p.heading_path]
        # Should contain hierarchical paths
        assert any("Main Title" in hp for hp in paths)
        assert any("Section One" in hp for hp in paths)
        assert any("Subsection A" in hp for hp in paths)

    def test_heading_path_hierarchy(self, tmp_md: Path) -> None:
        result = self.parser.parse(tmp_md)
        # Find the subsection A content paragraph
        subsec_paras = [
            p for p in result.paragraphs
            if p.heading_path and "Subsection A" in p.heading_path
        ]
        assert len(subsec_paras) > 0
        # heading_path should include parent
        hp = subsec_paras[0].heading_path
        assert "Main Title" in hp
        assert "Section One" in hp
        assert "Subsection A" in hp

    def test_section_two_resets_subsection(self, tmp_md: Path) -> None:
        result = self.parser.parse(tmp_md)
        sec2_paras = [
            p for p in result.paragraphs
            if p.heading_path and "Section Two" in p.heading_path
        ]
        assert len(sec2_paras) > 0
        # Section Two should NOT include Subsection A
        for p in sec2_paras:
            assert "Subsection A" not in (p.heading_path or "")

    def test_char_offsets(self, tmp_md: Path) -> None:
        result = self.parser.parse(tmp_md)
        for para in result.paragraphs:
            assert para.start_char >= 0
            assert para.end_char > para.start_char

    def test_chinese_headings(self, tmp_md_chinese: Path) -> None:
        result = self.parser.parse(tmp_md_chinese)
        assert result.parse_status == "success"
        assert result.title == "引言"
        paths = [p.heading_path for p in result.paragraphs if p.heading_path]
        assert any("引言" in hp for hp in paths)
        assert any("背景" in hp for hp in paths)

    def test_empty_file(self, tmp_md_empty: Path) -> None:
        result = self.parser.parse(tmp_md_empty)
        assert result.parse_status == "success"
        assert result.paragraphs == []

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
            p for p in result.paragraphs if p.heading_path and "Subsection A" in p.heading_path
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
            p for p in result.paragraphs if p.heading_path and "Section Two" in p.heading_path
        ]
        assert len(sec2_paras) > 0
        # Section Two should NOT include Subsection A
        for p in sec2_paras:
            assert "Subsection A" not in (p.heading_path or "")

    def test_char_offsets_exact(self, tmp_md: Path) -> None:
        result = self.parser.parse(tmp_md)
        for para in result.paragraphs:
            assert para.start_char >= 0
            assert para.end_char > para.start_char
            extracted = result.raw_text[para.start_char : para.end_char]
            assert extracted == para.text, (
                f"Offset mismatch: raw_text[{para.start_char}:{para.end_char}]="
                f"'{extracted}' != '{para.text}'"
            )

    def test_chinese_headings(self, tmp_md_chinese: Path) -> None:
        result = self.parser.parse(tmp_md_chinese)
        assert result.parse_status == "success"
        assert result.title == "引言"
        paths = [p.heading_path for p in result.paragraphs if p.heading_path]
        assert any("引言" in hp for hp in paths)
        assert any("背景" in hp for hp in paths)

    def test_empty_file(self, tmp_md_empty: Path) -> None:
        result = self.parser.parse(tmp_md_empty)
        assert result.parse_status == "failed"
        assert result.paragraphs == []
        assert result.error is not None
        assert result.error.code == "no_extractable_text"

    def test_fenced_code_block_not_heading(self, tmp_path: Path) -> None:
        """Lines starting with # inside fenced code blocks are not headings."""
        content = (
            "# Real Title\n"
            "\n"
            "Intro.\n"
            "\n"
            "```python\n"
            "# This is a comment, not a heading\n"
            "x = 1\n"
            "```\n"
            "\n"
            "After code.\n"
        )
        p = tmp_path / "code.md"
        p.write_text(content, encoding="utf-8")
        result = self.parser.parse(p)
        # The heading paths should only contain "Real Title"
        heading_paths = {para.heading_path for para in result.paragraphs if para.heading_path}
        for hp in heading_paths:
            assert "comment" not in hp.lower()
            assert "Real Title" in hp

    def test_tilde_fence_code_block(self, tmp_path: Path) -> None:
        """Tilde-fenced code blocks should also be handled."""
        content = "# Title\n\n~~~\n# not a heading\n~~~\n\nAfter.\n"
        p = tmp_path / "tilde.md"
        p.write_text(content, encoding="utf-8")
        result = self.parser.parse(p)
        heading_paths = {para.heading_path for para in result.paragraphs if para.heading_path}
        for hp in heading_paths:
            assert "not a heading" not in hp

    def test_heading_text_no_hash_prefix(self, tmp_md: Path) -> None:
        """Heading paragraph text must not contain raw '# ' markdown syntax."""
        result = self.parser.parse(tmp_md)
        for para in result.paragraphs:
            stripped = para.text.strip()
            if stripped:
                assert not stripped.startswith("# "), f"Heading leaked raw markdown: '{para.text}'"
                assert not stripped.startswith("## ")
                assert not stripped.startswith("### ")

    def test_chinese_char_offsets_exact(self, tmp_md_chinese: Path) -> None:
        """Chinese paragraphs must have exact char offsets in raw_text."""
        result = self.parser.parse(tmp_md_chinese)
        for para in result.paragraphs:
            assert para.start_char >= 0
            assert para.end_char > para.start_char
            extracted = result.raw_text[para.start_char : para.end_char]
            assert extracted == para.text, (
                f"Offset mismatch: raw_text[{para.start_char}:{para.end_char}]="
                f"'{extracted}' != '{para.text}'"
            )

    def test_long_fence_not_closed_by_short(self, tmp_path: Path) -> None:
        """A ````` (5-backtick) fence must NOT be closed by ``` (3-backtick)."""
        content = "# Title\n\n`````\n```\n# not a heading\n```\n`````\n\nAfter.\n"
        p = tmp_path / "longfence.md"
        p.write_text(content, encoding="utf-8")
        result = self.parser.parse(p)
        heading_paths = {para.heading_path for para in result.paragraphs if para.heading_path}
        for hp in heading_paths:
            assert "not a heading" not in hp

    def test_gbk_encoded_md(self, tmp_path: Path) -> None:
        """GBK-encoded .md file must be parsed without garbled text."""
        p = tmp_path / "gbk.md"
        content = "# 标题\n\n第一段内容。\n\n## 第二节\n\n更多内容。"
        p.write_bytes(content.encode("gbk"))
        result = self.parser.parse(p)
        assert result.parse_status == "success"
        assert "标题" in result.raw_text
        assert "\ufffd" not in result.raw_text

    def test_frontmatter_skipped(self, tmp_md_frontmatter: Path) -> None:
        """YAML frontmatter should not appear in parsed paragraphs."""
        result = self.parser.parse(tmp_md_frontmatter)
        assert result.parse_status == "success"
        assert result.title == "Actual Title"
        all_text = result.raw_text
        assert "title: My Document" not in all_text
        assert "date: 2026" not in all_text
        assert "Body content here." in all_text

    def test_frontmatter_offsets_valid(self, tmp_md_frontmatter: Path) -> None:
        """Paragraphs after frontmatter should have valid char offsets."""
        result = self.parser.parse(tmp_md_frontmatter)
        for para in result.paragraphs:
            extracted = result.raw_text[para.start_char : para.end_char]
            assert extracted == para.text

    def test_frontmatter_metadata_extracted(self, tmp_path: Path) -> None:
        content = (
            "---\n"
            "category: Project Plan\n"
            "tags:\n"
            "  - Roadmap\n"
            "  - Alpha\n"
            "sensitivity: Sensitive\n"
            "---\n"
            "\n"
            "# Actual Title\n"
            "\n"
            "Body content here.\n"
        )
        p = tmp_path / "metadata_frontmatter.md"
        p.write_text(content, encoding="utf-8")

        result = self.parser.parse(p)

        assert result.metadata.category == "project plan"
        assert result.metadata.tags == ["roadmap", "alpha"]
        assert result.metadata.sensitivity == "sensitive"
        assert result.title == "Actual Title"

    def test_indented_closing_fence(self, tmp_path: Path) -> None:
        """Closing fence with up to 3 spaces indent must be recognized."""
        content = (
            "# Title\n"
            "\n"
            "```\n"
            "# not a heading\n"
            "   ```\n"  # indented closing fence
            "\n"
            "## Real Section\n"
            "\n"
            "Content after fence.\n"
        )
        p = tmp_path / "indent_fence.md"
        p.write_text(content, encoding="utf-8")
        result = self.parser.parse(p)
        paths = [pp.heading_path for pp in result.paragraphs if pp.heading_path]
        assert any("Real Section" in hp for hp in paths)

    def test_setext_h1(self, tmp_path: Path) -> None:
        """Setext H1 (===) must be recognized as a heading."""
        content = "My Title\n========\n\nBody text.\n"
        p = tmp_path / "setext_h1.md"
        p.write_text(content, encoding="utf-8")
        result = self.parser.parse(p)
        assert result.title == "My Title"
        assert any(pp.heading_path and "My Title" in pp.heading_path for pp in result.paragraphs)

    def test_setext_h2(self, tmp_path: Path) -> None:
        """Setext H2 (---) must be recognized as a heading."""
        content = "# Top\n\nSubtitle\n--------\n\nBody.\n"
        p = tmp_path / "setext_h2.md"
        p.write_text(content, encoding="utf-8")
        result = self.parser.parse(p)
        paths = [pp.heading_path for pp in result.paragraphs if pp.heading_path]
        assert any("Subtitle" in hp for hp in paths)

    def test_atx_trailing_hashes_stripped(self, tmp_path: Path) -> None:
        """Trailing ## in ATX headings must be removed."""
        content = "# Title ##\n\n## Section ##\n\nContent.\n"
        p = tmp_path / "trailing_hash.md"
        p.write_text(content, encoding="utf-8")
        result = self.parser.parse(p)
        assert result.title == "Title"
        for pp in result.paragraphs:
            if pp.heading_path:
                assert "##" not in pp.heading_path

    def test_whitespace_only_markdown_is_failed(self, tmp_path: Path) -> None:
        p = tmp_path / "blank.md"
        p.write_text(" \n\n\t\n", encoding="utf-8")

        result = self.parser.parse(p)

        assert result.parse_status == "failed"
        assert result.paragraphs == []
        assert result.error is not None
        assert result.error.code == "no_extractable_text"

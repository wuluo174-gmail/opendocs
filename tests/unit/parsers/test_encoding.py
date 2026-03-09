"""Tests for encoding detection fallback."""

from __future__ import annotations

from pathlib import Path

from opendocs.parsers._encoding import read_text_with_fallback


class TestReadTextWithFallback:
    def test_utf8_file(self, tmp_path: Path) -> None:
        p = tmp_path / "utf8.txt"
        p.write_text("Hello 你好", encoding="utf-8")
        result = read_text_with_fallback(p)
        assert result == "Hello 你好"

    def test_gbk_file(self, tmp_path: Path) -> None:
        p = tmp_path / "gbk.txt"
        content = "这是GBK编码的中文文本。"
        p.write_bytes(content.encode("gbk"))
        result = read_text_with_fallback(p)
        assert "GBK" in result
        assert "中文" in result
        assert "\ufffd" not in result

    def test_gb18030_file(self, tmp_path: Path) -> None:
        p = tmp_path / "gb18030.txt"
        content = "这是GB18030编码。"
        p.write_bytes(content.encode("gb18030"))
        result = read_text_with_fallback(p)
        assert "GB18030" in result
        assert "\ufffd" not in result

    def test_latin1_file(self, tmp_path: Path) -> None:
        p = tmp_path / "latin1.txt"
        content = "café résumé naïve"
        p.write_bytes(content.encode("latin-1"))
        result = read_text_with_fallback(p)
        assert "café" in result or "caf" in result  # should not crash

    def test_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.txt"
        p.write_bytes(b"")
        result = read_text_with_fallback(p)
        assert result == ""

    def test_pure_ascii(self, tmp_path: Path) -> None:
        p = tmp_path / "ascii.txt"
        p.write_text("Hello World", encoding="ascii")
        result = read_text_with_fallback(p)
        assert result == "Hello World"

    def test_utf8_bom_stripped(self, tmp_path: Path) -> None:
        """UTF-8 BOM (EF BB BF) must be stripped automatically."""
        p = tmp_path / "bom.txt"
        p.write_bytes(b"\xef\xbb\xbfHello BOM")
        result = read_text_with_fallback(p)
        assert result == "Hello BOM"
        assert not result.startswith("\ufeff")

"""Tests for text normalization utilities."""

from __future__ import annotations

from opendocs.parsers.normalization import normalize_text


class TestNormalizeText:
    def test_nfc_normalization(self) -> None:
        # é as combining sequence (e + ´) → single codepoint
        combining = "e\u0301"  # e + combining acute
        result = normalize_text(combining)
        assert result == "\u00e9"  # é as single char

    def test_fullwidth_letters_digits_to_halfwidth(self) -> None:
        fullwidth = "ＡＢＣ１２３"
        result = normalize_text(fullwidth)
        assert result == "ABC123"

    def test_fullwidth_punctuation_preserved(self) -> None:
        """Chinese full-width punctuation must NOT be converted to half-width."""
        text = "你好，世界！这是（测试）。"
        result = normalize_text(text)
        assert "，" in result
        assert "！" in result
        assert "（" in result
        assert "）" in result

    def test_fullwidth_space(self) -> None:
        text = "你好\u3000世界"
        result = normalize_text(text)
        assert result == "你好 世界"

    def test_collapse_spaces_but_preserve_tabs(self) -> None:
        text = "hello   world\t\there"
        result = normalize_text(text)
        assert result == "hello world\t\there"

    def test_preserve_newlines(self) -> None:
        text = "line1\n\nline2"
        result = normalize_text(text)
        assert result == "line1\n\nline2"

    def test_strip_trailing_whitespace(self) -> None:
        text = "hello   \nworld   "
        result = normalize_text(text)
        assert result == "hello\nworld"

    def test_chinese_text_unchanged(self) -> None:
        text = "这是一段中文文本。"
        result = normalize_text(text)
        assert result == text

    def test_empty_string(self) -> None:
        assert normalize_text("") == ""

"""Tests for ParserRegistry and failure isolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from opendocs.parsers import create_default_registry
from opendocs.parsers.base import ParserRegistry
from opendocs.parsers.txt_parser import TxtParser


class TestParserRegistry:
    def test_register_and_lookup(self) -> None:
        registry = ParserRegistry()
        registry.register(TxtParser())
        assert registry.is_supported("test.txt")
        assert registry.get_parser("test.txt") is not None

    def test_unsupported_format(self) -> None:
        registry = ParserRegistry()
        assert not registry.is_supported("test.xyz")
        assert registry.get_parser("test.xyz") is None

    def test_create_default_registry(self) -> None:
        registry = create_default_registry()
        assert registry.is_supported("file.txt")
        assert registry.is_supported("file.md")
        assert registry.is_supported("file.docx")
        assert registry.is_supported("file.pdf")
        assert not registry.is_supported("file.xyz")


class TestFailureIsolation:
    """Registry.parse() should never raise – it returns failed ParsedDocument."""

    def test_unsupported_format_no_exception(self, tmp_path: Path) -> None:
        registry = create_default_registry()
        p = tmp_path / "test.xyz"
        p.write_text("hello")
        result = registry.parse(p)
        assert result.parse_status == "failed"
        assert "unsupported format" in result.error_info

    def test_empty_file_no_exception(self, tmp_path: Path) -> None:
        registry = create_default_registry()
        p = tmp_path / "empty.txt"
        p.write_text("")
        result = registry.parse(p)
        assert result.parse_status == "failed"
        assert result.error_info == "empty file"

    def test_missing_file_no_exception(self, tmp_path: Path) -> None:
        registry = create_default_registry()
        p = tmp_path / "nonexistent.txt"
        result = registry.parse(p)
        assert result.parse_status == "failed"
        assert result.error_info is not None

    def test_corrupted_docx_no_exception(self, tmp_path: Path) -> None:
        registry = create_default_registry()
        p = tmp_path / "bad.docx"
        p.write_bytes(b"not a docx file")
        result = registry.parse(p)
        assert result.parse_status == "failed"
        assert result.error_info is not None

    def test_corrupted_pdf_no_exception(self, tmp_path: Path) -> None:
        registry = create_default_registry()
        p = tmp_path / "bad.pdf"
        p.write_bytes(b"not a pdf")
        result = registry.parse(p)
        assert result.parse_status == "failed"
        assert result.error_info is not None

    def test_permission_denied_no_exception(self, tmp_path: Path) -> None:
        registry = create_default_registry()
        p = tmp_path / "noperm.txt"
        p.write_text("content")
        p.chmod(0o000)
        try:
            result = registry.parse(p)
            assert result.parse_status == "failed"
        finally:
            p.chmod(0o644)

    def test_batch_processing_never_crashes(self, tmp_path: Path) -> None:
        """Simulate batch: mix of good, bad, and unsupported files."""
        registry = create_default_registry()

        good = tmp_path / "good.txt"
        good.write_text("Hello world")

        bad = tmp_path / "bad.docx"
        bad.write_bytes(b"corrupt")

        unsup = tmp_path / "file.xyz"
        unsup.write_text("data")

        results = [registry.parse(f) for f in [good, bad, unsup]]
        # No exception raised – all results returned
        assert len(results) == 3
        assert results[0].parse_status == "success"
        assert results[1].parse_status == "failed"
        assert results[2].parse_status == "failed"

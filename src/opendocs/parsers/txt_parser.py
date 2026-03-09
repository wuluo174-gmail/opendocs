"""Plain-text document parser."""

from __future__ import annotations

import re
from pathlib import Path

from opendocs.parsers._encoding import read_text_with_fallback
from opendocs.parsers.base import BaseParser, Paragraph, ParsedDocument


class TxtParser(BaseParser):
    """Parse plain ``.txt`` files."""

    def supported_extensions(self) -> list[str]:
        return [".txt"]

    def parse(self, file_path: Path) -> ParsedDocument:
        text = read_text_with_fallback(file_path)

        # Split by double newline (blank-line separated paragraphs)
        raw_paragraphs = re.split(r"\n\s*\n", text)

        # Collect stripped, non-empty entries
        entries: list[str] = []
        for raw in raw_paragraphs:
            stripped = raw.strip()
            if stripped:
                entries.append(stripped)

        # Build raw_text from entries and compute offsets cumulatively
        raw_text = "\n".join(entries)
        paragraphs: list[Paragraph] = []
        offset = 0
        for idx, entry in enumerate(entries):
            start = offset
            end = offset + len(entry)
            paragraphs.append(
                Paragraph(
                    text=entry,
                    index=idx,
                    start_char=start,
                    end_char=end,
                )
            )
            offset = end + 1  # +1 for the \n separator

        # Title = first non-empty entry
        title = entries[0] if entries else None

        return ParsedDocument(
            file_path=str(file_path),
            file_type="txt",
            raw_text=raw_text,
            title=title,
            paragraphs=paragraphs,
        )

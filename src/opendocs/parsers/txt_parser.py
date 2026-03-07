"""Plain-text document parser."""

from __future__ import annotations

import re
from pathlib import Path

from opendocs.parsers.base import BaseParser, Paragraph, ParsedDocument


class TxtParser(BaseParser):
    """Parse plain ``.txt`` files."""

    def supported_extensions(self) -> list[str]:
        return [".txt"]

    def parse(self, file_path: Path) -> ParsedDocument:
        text = file_path.read_text(encoding="utf-8", errors="replace")

        # Split by double newline (blank-line separated paragraphs)
        raw_paragraphs = re.split(r"\n\s*\n", text)

        paragraphs: list[Paragraph] = []
        offset = 0
        idx = 0
        remaining = text

        for raw in raw_paragraphs:
            stripped = raw.strip()
            if not stripped:
                # advance offset past the empty segment
                pos = remaining.find(raw)
                if pos >= 0:
                    offset += pos + len(raw)
                    remaining = text[offset:]
                continue

            # Find position of this paragraph text in remaining text
            pos = remaining.find(raw)
            if pos < 0:
                # fallback: find stripped version
                pos = remaining.find(stripped)
                if pos >= 0:
                    start = offset + pos
                    end = start + len(stripped)
                else:
                    start = offset
                    end = start + len(stripped)
            else:
                start = offset + pos
                end = start + len(raw)

            paragraphs.append(
                Paragraph(
                    text=stripped,
                    index=idx,
                    start_char=start,
                    end_char=end,
                )
            )
            idx += 1

            # Advance offset past this paragraph
            new_offset = start + len(raw)
            if new_offset > offset:
                offset = new_offset
                remaining = text[offset:]

        # Title = first non-empty line
        title = None
        for line in text.splitlines():
            line_stripped = line.strip()
            if line_stripped:
                title = line_stripped
                break

        return ParsedDocument(
            file_path=str(file_path),
            file_type="txt",
            raw_text=text,
            title=title,
            paragraphs=paragraphs,
        )

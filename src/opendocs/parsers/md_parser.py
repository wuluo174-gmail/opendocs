"""Markdown document parser with heading hierarchy tracking."""

from __future__ import annotations

import re
from pathlib import Path

from opendocs.parsers.base import BaseParser, Paragraph, ParsedDocument

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


class MdParser(BaseParser):
    """Parse ``.md`` (Markdown) files, extracting heading paths."""

    def supported_extensions(self) -> list[str]:
        return [".md"]

    def parse(self, file_path: Path) -> ParsedDocument:
        text = file_path.read_text(encoding="utf-8", errors="replace")

        paragraphs: list[Paragraph] = []
        title: str | None = None

        # Heading stack: list of (level, title_text)
        heading_stack: list[tuple[int, str]] = []
        current_heading_path: str | None = None

        # Accumulator for paragraph text between headings / blank lines
        buf_lines: list[str] = []
        buf_start: int | None = None
        offset = 0  # character offset into text
        idx = 0

        def _flush() -> None:
            nonlocal idx
            if not buf_lines:
                return
            joined = "\n".join(buf_lines).strip()
            if not joined:
                return
            assert buf_start is not None
            paragraphs.append(
                Paragraph(
                    text=joined,
                    index=idx,
                    start_char=buf_start,
                    end_char=buf_start + len("\n".join(buf_lines).rstrip()),
                    heading_path=current_heading_path,
                )
            )
            idx += 1

        lines = text.split("\n")
        for line in lines:
            m = _HEADING_RE.match(line)
            if m:
                # Flush previous paragraph
                _flush()
                buf_lines.clear()
                buf_start = None

                level = len(m.group(1))
                heading_text = m.group(2).strip()

                # Set title to first H1
                if title is None and level == 1:
                    title = heading_text

                # Update heading stack
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, heading_text))

                current_heading_path = " > ".join(h[1] for h in heading_stack)

                # The heading line itself becomes a paragraph
                paragraphs.append(
                    Paragraph(
                        text=line.strip(),
                        index=idx,
                        start_char=offset,
                        end_char=offset + len(line),
                        heading_path=current_heading_path,
                    )
                )
                idx += 1

            elif line.strip() == "":
                # Blank line: flush current buffer
                _flush()
                buf_lines.clear()
                buf_start = None
            else:
                if buf_start is None:
                    buf_start = offset
                buf_lines.append(line)

            # Advance offset (account for the \n we split on)
            offset += len(line) + 1  # +1 for the newline

        # Flush remaining
        _flush()

        # If no H1 title, use first non-empty line
        if title is None:
            for line in lines:
                s = line.strip()
                if s:
                    title = s
                    break

        return ParsedDocument(
            file_path=str(file_path),
            file_type="md",
            raw_text=text,
            title=title,
            paragraphs=paragraphs,
        )

"""Markdown document parser with heading hierarchy tracking."""

from __future__ import annotations

import re
from pathlib import Path

from opendocs.parsers._encoding import read_text_with_fallback
from opendocs.parsers.base import BaseParser, Paragraph, ParsedDocument

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_FRONTMATTER_SEP = re.compile(r"^-{3,}\s*$")
_SETEXT_H1_RE = re.compile(r"^={1,}\s*$")
_SETEXT_H2_RE = re.compile(r"^-{1,}\s*$")
_TRAILING_HASHES_RE = re.compile(r"\s+#+\s*$")


class MdParser(BaseParser):
    """Parse ``.md`` (Markdown) files, extracting heading paths."""

    def supported_extensions(self) -> list[str]:
        return [".md"]

    def parse(self, file_path: Path) -> ParsedDocument:
        text = read_text_with_fallback(file_path)

        title: str | None = None

        # Heading stack: list of (level, title_text)
        heading_stack: list[tuple[int, str]] = []
        current_heading_path: str | None = None

        # First pass: collect (text, heading_path) entries
        entries: list[tuple[str, str | None]] = []
        buf_lines: list[str] = []
        in_fence = False
        fence_marker = ""
        fence_open_len = 0

        def _flush() -> None:
            if not buf_lines:
                return
            joined = "\n".join(buf_lines).strip()
            if not joined:
                return
            entries.append((joined, current_heading_path))

        lines = text.split("\n")

        # Skip YAML frontmatter (--- ... ---)
        line_start = 0
        if lines and _FRONTMATTER_SEP.match(lines[0]):
            for i in range(1, len(lines)):
                if _FRONTMATTER_SEP.match(lines[i]):
                    line_start = i + 1
                    break

        for line in lines[line_start:]:
            # Track fenced code blocks so we don't treat `# comment` as headings
            fence_match = _FENCE_RE.match(line)
            if fence_match:
                marker_char = fence_match.group(1)[0]
                marker_len = len(fence_match.group(1))
                if not in_fence:
                    in_fence = True
                    fence_marker = marker_char
                    fence_open_len = marker_len
                    buf_lines.append(line)
                    continue
                elif marker_char == fence_marker and marker_len >= fence_open_len:
                    # CommonMark: closing fence must be >= opening fence length
                    in_fence = False
                    fence_marker = ""
                    fence_open_len = 0
                    buf_lines.append(line)
                    continue

            if in_fence:
                buf_lines.append(line)
                continue

            # Setext-style heading: previous buffer has exactly one non-empty
            # line and current line is === or ---
            setext_level = 0
            if len(buf_lines) == 1 and buf_lines[0].strip() and not in_fence:
                if _SETEXT_H1_RE.match(line):
                    setext_level = 1
                elif _SETEXT_H2_RE.match(line):
                    setext_level = 2

            if setext_level:
                heading_text = buf_lines[0].strip()
                buf_lines.clear()

                if title is None and setext_level == 1:
                    title = heading_text

                while heading_stack and heading_stack[-1][0] >= setext_level:
                    heading_stack.pop()
                heading_stack.append((setext_level, heading_text))
                current_heading_path = " > ".join(h[1] for h in heading_stack)
                entries.append((heading_text, current_heading_path))
                continue

            m = _HEADING_RE.match(line)
            if m:
                # Flush previous paragraph
                _flush()
                buf_lines.clear()

                level = len(m.group(1))
                heading_text = _TRAILING_HASHES_RE.sub("", m.group(2)).strip()

                # Set title to first H1
                if title is None and level == 1:
                    title = heading_text

                # Update heading stack
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, heading_text))

                current_heading_path = " > ".join(h[1] for h in heading_stack)

                # Design choice: heading text is emitted as an independent
                # paragraph.  This may produce very short entries that the
                # chunker merges into adjacent chunks.  Because the heading
                # itself is the boundary point for heading_path changes, it
                # may sometimes form a standalone chunk.  Accepted trade-off:
                # keeps heading_path transitions clean and avoids mixing
                # heading text with the body paragraph that follows.
                entries.append((heading_text, current_heading_path))

            elif line.strip() == "":
                # Blank line: flush current buffer
                _flush()
                buf_lines.clear()
            else:
                buf_lines.append(line)

        # Flush remaining
        _flush()

        # If no H1 title, use first non-empty entry
        if title is None:
            for entry_text, _ in entries:
                s = entry_text.strip()
                if s:
                    title = s
                    break

        # Second pass: build raw_text and compute offsets cumulatively
        raw_text = "\n".join(e[0] for e in entries)
        paragraphs: list[Paragraph] = []
        offset = 0
        for idx, (entry_text, heading_path) in enumerate(entries):
            start = offset
            end = offset + len(entry_text)
            paragraphs.append(
                Paragraph(
                    text=entry_text,
                    index=idx,
                    start_char=start,
                    end_char=end,
                    heading_path=heading_path,
                )
            )
            offset = end + 1  # +1 for the \n separator

        return ParsedDocument(
            file_path=str(file_path),
            file_type="md",
            raw_text=raw_text,
            title=title,
            paragraphs=paragraphs,
        )

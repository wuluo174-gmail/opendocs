"""Word (.docx) document parser using python-docx."""

from __future__ import annotations

import re
from pathlib import Path

from opendocs.exceptions import ParseFailedError
from opendocs.parsers.base import BaseParser, Paragraph, ParsedDocument

_HEADING_STYLE_RE = re.compile(r"^Heading\s*(\d+)$", re.IGNORECASE)


class DocxParser(BaseParser):
    """Parse ``.docx`` files via *python-docx*."""

    def supported_extensions(self) -> list[str]:
        return [".docx"]

    def parse(self, file_path: Path) -> ParsedDocument:
        try:
            from docx import Document  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ParseFailedError(
                "python-docx is not installed"
            ) from exc

        try:
            doc = Document(str(file_path))
        except Exception as exc:
            raise ParseFailedError(f"Failed to open docx: {exc}") from exc

        heading_stack: list[tuple[int, str]] = []
        current_heading_path: str | None = None
        paragraphs: list[Paragraph] = []
        raw_parts: list[str] = []
        offset = 0
        idx = 0
        title: str | None = None

        # Try document core properties title first
        try:
            if doc.core_properties.title:
                title = doc.core_properties.title
        except Exception:  # noqa: BLE001
            pass

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                # Still account for the newline separator
                raw_parts.append("")
                offset += 1  # for the \n
                continue

            style_name = para.style.name if para.style else ""
            m = _HEADING_STYLE_RE.match(style_name)

            if m:
                level = int(m.group(1))
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, text))
                current_heading_path = " > ".join(h[1] for h in heading_stack)

                if title is None:
                    title = text

            start = offset
            end = offset + len(text)

            paragraphs.append(
                Paragraph(
                    text=text,
                    index=idx,
                    start_char=start,
                    end_char=end,
                    heading_path=current_heading_path,
                )
            )
            idx += 1
            raw_parts.append(text)
            offset = end + 1  # +1 for newline separator

        raw_text = "\n".join(raw_parts)

        return ParsedDocument(
            file_path=str(file_path),
            file_type="docx",
            raw_text=raw_text,
            title=title,
            paragraphs=paragraphs,
        )

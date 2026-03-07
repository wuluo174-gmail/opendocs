"""PDF document parser (text layer only).

Prefers PyMuPDF (fitz), falls back to pypdf.
"""

from __future__ import annotations

import re
from pathlib import Path

from opendocs.exceptions import ParseFailedError
from opendocs.parsers.base import BaseParser, Paragraph, ParsedDocument


def _try_fitz(file_path: Path) -> tuple[list[tuple[int, str]], str | None, int]:
    """Extract pages with PyMuPDF. Returns (pages, title, page_count).

    Each page is ``(page_number_1based, text)``.
    """
    import fitz  # type: ignore[import-untyped]

    doc = fitz.open(str(file_path))
    title = doc.metadata.get("title") if doc.metadata else None
    page_count = len(doc)
    pages: list[tuple[int, str]] = []
    for i, page in enumerate(doc):
        pages.append((i + 1, page.get_text()))
    doc.close()
    return pages, title or None, page_count


def _try_pypdf(file_path: Path) -> tuple[list[tuple[int, str]], str | None, int]:
    """Extract pages with pypdf. Returns (pages, title, page_count)."""
    from pypdf import PdfReader  # type: ignore[import-untyped]

    reader = PdfReader(str(file_path))
    title = None
    if reader.metadata and reader.metadata.title:
        title = reader.metadata.title
    page_count = len(reader.pages)
    pages: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append((i + 1, text))
    return pages, title or None, page_count


class PdfParser(BaseParser):
    """Parse ``.pdf`` files (text layer only, no OCR)."""

    def supported_extensions(self) -> list[str]:
        return [".pdf"]

    def parse(self, file_path: Path) -> ParsedDocument:
        pages: list[tuple[int, str]]
        title: str | None
        page_count: int

        try:
            pages, title, page_count = _try_fitz(file_path)
        except ImportError:
            try:
                pages, title, page_count = _try_pypdf(file_path)
            except ImportError as exc:
                raise ParseFailedError(
                    "Neither PyMuPDF nor pypdf is installed"
                ) from exc
            except Exception as exc:
                raise ParseFailedError(f"pypdf failed: {exc}") from exc
        except Exception as exc:
            # fitz failed for a non-import reason; try pypdf
            try:
                pages, title, page_count = _try_pypdf(file_path)
            except Exception:
                raise ParseFailedError(f"PDF extraction failed: {exc}") from exc

        # Build paragraphs from pages
        paragraphs: list[Paragraph] = []
        raw_parts: list[str] = []
        offset = 0
        idx = 0

        for page_no, page_text in pages:
            # Split page into paragraphs by blank lines
            segments = re.split(r"\n\s*\n", page_text)
            for seg in segments:
                stripped = seg.strip()
                if not stripped:
                    continue
                start = offset
                end = offset + len(stripped)
                paragraphs.append(
                    Paragraph(
                        text=stripped,
                        index=idx,
                        start_char=start,
                        end_char=end,
                        page_no=page_no,
                    )
                )
                idx += 1
                raw_parts.append(stripped)
                offset = end + 1  # +1 for newline separator

        raw_text = "\n".join(raw_parts)

        # Fallback title: first non-empty line
        if not title and raw_text:
            for line in raw_text.splitlines():
                s = line.strip()
                if s:
                    title = s
                    break

        return ParsedDocument(
            file_path=str(file_path),
            file_type="pdf",
            raw_text=raw_text,
            title=title,
            paragraphs=paragraphs,
            page_count=page_count,
        )

"""PDF document parser (text layer only).

Prefers PyMuPDF (fitz), falls back to pypdf.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from opendocs.exceptions import ParseFailedError
from opendocs.parsers.base import BaseParser, Paragraph, ParsedDocument, ParseError

logger = logging.getLogger(__name__)


@dataclass
class _TocEntry:
    """A Table-of-Contents entry from the PDF."""

    level: int  # heading level (1-based)
    title: str
    page_no: int  # 1-based page number


@dataclass
class _PdfExtraction:
    """Internal result from a PDF backend."""

    pages: list[tuple[int, str]]  # (page_number_1based, text)
    title: str | None
    page_count: int
    failed_pages: list[int]  # 1-based page numbers that failed
    toc: list[_TocEntry]  # table of contents (may be empty)
    empty_pages: list[int] = field(default_factory=list)  # extracted but yielded no text


def _try_fitz(file_path: Path) -> _PdfExtraction:
    """Extract pages with PyMuPDF."""
    import fitz  # type: ignore[import-untyped]

    with fitz.open(str(file_path)) as doc:
        title = doc.metadata.get("title") if doc.metadata else None
        page_count = len(doc)
        pages: list[tuple[int, str]] = []
        failed_pages: list[int] = []
        empty_pages: list[int] = []
        for i, page in enumerate(doc):
            try:
                page_text = page.get_text()
                pages.append((i + 1, page_text))
                if not page_text.strip():
                    empty_pages.append(i + 1)
            except Exception:  # noqa: BLE001
                failed_pages.append(i + 1)

        # Extract TOC (bookmarks) for heading_path support
        toc: list[_TocEntry] = []
        try:
            for level, heading, page_no in doc.get_toc():
                toc.append(_TocEntry(level=level, title=heading.strip(), page_no=page_no))
        except Exception:  # noqa: BLE001
            pass

    return _PdfExtraction(
        pages,
        title or None,
        page_count,
        failed_pages,
        toc,
        empty_pages=empty_pages,
    )


def _try_pypdf(file_path: Path) -> _PdfExtraction:
    """Extract pages with pypdf."""
    from pypdf import PdfReader  # type: ignore[import-untyped]

    reader = PdfReader(str(file_path))
    title = None
    if reader.metadata and reader.metadata.title:
        title = reader.metadata.title
    page_count = len(reader.pages)
    pages: list[tuple[int, str]] = []
    failed_pages: list[int] = []
    empty_pages: list[int] = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
            pages.append((i + 1, text))
            if not text.strip():
                empty_pages.append(i + 1)
        except Exception:  # noqa: BLE001
            failed_pages.append(i + 1)
    # pypdf has no convenient TOC API; return empty
    return _PdfExtraction(
        pages,
        title or None,
        page_count,
        failed_pages,
        toc=[],
        empty_pages=empty_pages,
    )


class PdfParser(BaseParser):
    """Parse ``.pdf`` files (text layer only, no OCR)."""

    def supported_extensions(self) -> list[str]:
        return [".pdf"]

    def parse(self, file_path: Path) -> ParsedDocument:
        extraction: _PdfExtraction
        fallback_details: dict[str, object] | None = None
        fallback_message: str | None = None

        try:
            extraction = _try_fitz(file_path)
        except ImportError as exc:
            try:
                extraction = _try_pypdf(file_path)
                fallback_message = (
                    "PyMuPDF unavailable; fell back to pypdf and heading_path "
                    "(TOC bookmarks) is unavailable"
                )
                fallback_details = {
                    "parser": "PdfParser",
                    "failed_backend": "PyMuPDF",
                    "fallback_backend": "pypdf",
                    "fitz_error": str(exc),
                    "degraded_fields": ["heading_path"],
                }
            except ImportError as exc:
                raise ParseFailedError("Neither PyMuPDF nor pypdf is installed") from exc
            except Exception as exc:
                raise ParseFailedError(f"pypdf failed: {exc}") from exc
        except Exception as exc:
            try:
                extraction = _try_pypdf(file_path)
                fallback_message = (
                    "PyMuPDF failed; fell back to pypdf and heading_path "
                    "(TOC bookmarks) is unavailable"
                )
                fallback_details = {
                    "parser": "PdfParser",
                    "failed_backend": "PyMuPDF",
                    "fallback_backend": "pypdf",
                    "fitz_error": str(exc),
                    "degraded_fields": ["heading_path"],
                }
                logger.warning(
                    "PyMuPDF failed for %s, fell back to pypdf; "
                    "heading_path (TOC bookmarks) will not be available",
                    file_path,
                )
            except Exception as pypdf_exc:
                raise ParseFailedError(
                    f"PDF extraction failed: fitz={exc}, pypdf={pypdf_exc}"
                ) from pypdf_exc

        # Build a page→heading_path lookup from TOC entries
        # For each page, compute the heading_path that applies (last TOC
        # entry whose page_no <= current page).
        page_heading: dict[int, str] = {}
        if extraction.toc:
            heading_stack: list[tuple[int, str]] = []
            # Sort TOC by page only; Python's stable sort preserves the
            # original document order for entries on the same page.
            sorted_toc = sorted(extraction.toc, key=lambda e: e.page_no)
            toc_idx = 0
            max_page = max(p for p, _ in extraction.pages) if extraction.pages else 0
            for pg in range(1, max_page + 1):
                while toc_idx < len(sorted_toc) and sorted_toc[toc_idx].page_no <= pg:
                    entry = sorted_toc[toc_idx]
                    while heading_stack and heading_stack[-1][0] >= entry.level:
                        heading_stack.pop()
                    heading_stack.append((entry.level, entry.title))
                    toc_idx += 1
                if heading_stack:
                    page_heading[pg] = " > ".join(h[1] for h in heading_stack)

        # Build paragraphs from pages
        paragraphs: list[Paragraph] = []
        raw_parts: list[str] = []
        offset = 0
        idx = 0

        for page_no, page_text in extraction.pages:
            heading_path = page_heading.get(page_no)
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
                        heading_path=heading_path,
                    )
                )
                idx += 1
                raw_parts.append(stripped)
                offset = end + 1  # +1 for newline separator

        raw_text = "\n".join(raw_parts)

        # Fallback title: first non-empty line
        title = extraction.title
        if not title and raw_text:
            for line in raw_text.splitlines():
                s = line.strip()
                if s:
                    title = s
                    break

        # Determine parse status
        failed_pages = extraction.failed_pages
        empty_pages = extraction.empty_pages
        parse_status: Literal["success", "partial", "failed"]
        error: ParseError | None = None
        if failed_pages and not extraction.pages:
            parse_status = "failed"
            error_info = f"all pages failed: {failed_pages}"
            error = ParseError(
                code="parse_failed",
                message=error_info,
                details={"parser": "PdfParser", "failed_pages": failed_pages},
            )
        elif not raw_text.strip():
            parse_status = "failed"
            error_info = "no extractable text layer"
            error = ParseError(
                code="no_text_layer",
                message=error_info,
                details={
                    "parser": "PdfParser",
                    "page_count": extraction.page_count,
                    "failed_pages": failed_pages,
                    "empty_pages": empty_pages,
                },
            )
        elif failed_pages or empty_pages:
            parse_status = "partial"
            status_parts: list[str] = []
            if failed_pages:
                status_parts.append(f"failed pages: {failed_pages}")
            if empty_pages:
                status_parts.append(f"no text extracted on pages: {empty_pages}")
            error_info = "; ".join(status_parts)
            error = ParseError(
                code="partial_parse",
                message=error_info,
                details={
                    "parser": "PdfParser",
                    "failed_pages": failed_pages,
                    "empty_pages": empty_pages,
                },
            )
        else:
            parse_status = "success"
            error_info = None

        if fallback_details is not None and fallback_message is not None:
            if error_info is None:
                error_info = fallback_message
            else:
                error_info = f"{error_info}; {fallback_message}"

            if error is None:
                error = ParseError(
                    code="partial_parse",
                    message=error_info,
                    details=fallback_details,
                )
            else:
                error = ParseError(
                    code=error.code,
                    message=error_info,
                    details={**error.details, **fallback_details},
                )

            if parse_status == "success":
                parse_status = "partial"

        return ParsedDocument(
            file_path=str(file_path),
            file_type="pdf",
            raw_text=raw_text,
            title=title,
            paragraphs=paragraphs,
            page_count=extraction.page_count,
            parse_status=parse_status,
            error_info=error_info,
            error=error,
        )

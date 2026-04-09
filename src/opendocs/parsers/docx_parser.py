"""Word (.docx) document parser using python-docx."""

from __future__ import annotations

import re
from pathlib import Path

from opendocs.domain.document_metadata import DocumentMetadata
from opendocs.exceptions import ParseFailedError
from opendocs.parsers.base import (
    BaseParser,
    Paragraph,
    ParsedDocument,
    ParseError,
)

_HEADING_STYLE_RE = re.compile(r"^Heading\s*(\d+)$", re.IGNORECASE)


def _split_keywords(value: str | None) -> list[str]:
    if value is None:
        return []
    parts = re.split(r"[;,]", value)
    return [part.strip() for part in parts if part.strip()]


def _extract_paragraph_text(para_element, qn) -> str:
    """Flatten a ``w:p`` element while preserving inline control characters."""
    parts: list[str] = []
    for node in para_element.iter():
        tag = getattr(node, "tag", None)
        if tag == qn("w:t"):
            if node.text:
                parts.append(node.text)
        elif tag == qn("w:tab"):
            parts.append("\t")
        elif tag in {qn("w:br"), qn("w:cr")}:
            parts.append("\n")
    return "".join(parts).strip()


class DocxParser(BaseParser):
    """Parse ``.docx`` files via *python-docx*."""

    def supported_extensions(self) -> list[str]:
        return [".docx"]

    def _parse_raw(self, file_path: Path) -> ParsedDocument:
        try:
            from docx import Document  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ParseFailedError("python-docx is not installed") from exc

        try:
            doc = Document(str(file_path))
        except Exception as exc:
            raise ParseFailedError(f"Failed to open docx: {exc}") from exc

        heading_stack: list[tuple[int, str]] = []
        current_heading_path: str | None = None
        title: str | None = None
        metadata = DocumentMetadata()
        failed_source_paras: list[int] = []
        failed_tables: list[int] = []

        # Try document core properties title first
        try:
            if doc.core_properties.title:
                title = doc.core_properties.title
        except Exception:  # noqa: BLE001
            pass

        try:
            metadata = DocumentMetadata(
                category=doc.core_properties.category,
                tags=_split_keywords(doc.core_properties.keywords),
            )
        except Exception:  # noqa: BLE001
            metadata = DocumentMetadata()

        # Iterate doc.element.body children in document order so that
        # tables inherit the heading_path of the heading that precedes them
        # (not the last heading in the entire document).
        from docx.oxml.ns import qn  # type: ignore[import-untyped]
        from docx.table import Table  # type: ignore[import-untyped]

        entries: list[tuple[str, str | None]] = []  # (text, heading_path)
        xml_para_idx = 0  # counts all w:p elements (for internal tracking)
        table_block_idx = 0
        for child in doc.element.body:
            tag = child.tag

            if tag == qn("w:p"):
                # Paragraph element
                try:
                    text = _extract_paragraph_text(child, qn)
                except Exception:  # noqa: BLE001
                    # Record source-order paragraph indices from the original
                    # document stream. Failed paragraphs are omitted from the
                    # final result, so returned Paragraph.index values cannot
                    # reliably point to them.
                    failed_source_paras.append(xml_para_idx)
                    xml_para_idx += 1
                    continue

                xml_para_idx += 1
                if not text:
                    continue

                # Determine style name from XML
                pPr = child.find(qn("w:pPr"))
                style_name = ""
                if pPr is not None:
                    pStyle = pPr.find(qn("w:pStyle"))
                    if pStyle is not None:
                        style_name = pStyle.get(qn("w:val"), "")

                m = _HEADING_STYLE_RE.match(style_name)
                if m:
                    level = int(m.group(1))
                    while heading_stack and heading_stack[-1][0] >= level:
                        heading_stack.pop()
                    heading_stack.append((level, text))
                    current_heading_path = " > ".join(h[1] for h in heading_stack)

                    if title is None and level == 1:
                        title = text

                entries.append((text, current_heading_path))

            elif tag == qn("w:tbl"):
                # Table element — process rows in document order
                try:
                    table = Table(child, doc)
                    for row in table.rows:
                        cells_text: list[str] = []
                        for cell in row.cells:
                            try:
                                ct = cell.text.strip()
                            except Exception:  # noqa: BLE001
                                continue
                            if ct:
                                cells_text.append(ct)
                        if cells_text:
                            row_text = " | ".join(cells_text)
                            entries.append((row_text, current_heading_path))
                except Exception:  # noqa: BLE001
                    failed_tables.append(table_block_idx)
                finally:
                    table_block_idx += 1

        # If no Heading 1 title and no core_properties title, use first entry
        if title is None and entries:
            title = entries[0][0]

        # Build raw_text then compute offsets from it
        raw_text = "\n".join(e[0] for e in entries)
        paragraphs: list[Paragraph] = []
        offset = 0
        for idx, (text, heading_path) in enumerate(entries):
            start = offset
            end = offset + len(text)
            paragraphs.append(
                Paragraph(
                    text=text,
                    index=idx,
                    start_char=start,
                    end_char=end,
                    heading_path=heading_path,
                )
            )
            offset = end + 1  # +1 for the \n separator

        # Determine parse status
        failure_messages: list[str] = []
        if failed_source_paras:
            failure_messages.append(f"failed source paragraphs at indices: {failed_source_paras}")
        if failed_tables:
            failure_messages.append(f"failed table blocks: {failed_tables}")

        error: ParseError | None = None
        if failure_messages and not entries:
            parse_status = "failed"
            error_info = "; ".join(failure_messages)
            error = ParseError(
                code="parse_failed",
                message=error_info,
                details={
                    "parser": "DocxParser",
                    "failed_source_paragraph_indices": failed_source_paras,
                    "failed_table_blocks": failed_tables,
                },
            )
        elif failure_messages:
            parse_status = "partial"
            error_info = "; ".join(failure_messages)
            error = ParseError(
                code="partial_parse",
                message=error_info,
                details={
                    "parser": "DocxParser",
                    "failed_source_paragraph_indices": failed_source_paras,
                    "failed_table_blocks": failed_tables,
                },
            )
        else:
            parse_status = "success"
            error_info = None

        return ParsedDocument(
            file_path=str(file_path),
            file_type="docx",
            raw_text=raw_text,
            title=title,
            paragraphs=paragraphs,
            parse_status=parse_status,
            error_info=error_info,
            error=error,
            metadata=metadata,
        )

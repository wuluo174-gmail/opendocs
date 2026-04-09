"""ParsedDocument model, Paragraph dataclass, BaseParser ABC, and ParserRegistry."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from opendocs.domain.document_metadata import DocumentMetadata
from opendocs.exceptions import ParseFailedError, ParseUnsupportedError
from opendocs.parsers.normalization import normalize_text

logger = logging.getLogger(__name__)


@dataclass
class Paragraph:
    """A single paragraph extracted from a document."""

    text: str
    index: int  # 段落序号（从 0 开始）
    start_char: int  # 在 raw_text 中的起始偏移
    end_char: int  # 在 raw_text 中的结束偏移
    page_no: int | None = None  # PDF 页码（从 1 开始），非 PDF 为 None
    heading_path: str | None = None  # 如 "引言 > 背景 > 历史"

    def __post_init__(self) -> None:
        if self.start_char < 0:
            raise ValueError(f"start_char must be >= 0, got {self.start_char}")
        if self.end_char < self.start_char:
            raise ValueError(
                f"end_char ({self.end_char}) must be >= start_char ({self.start_char})"
            )
        if self.index < 0:
            raise ValueError(f"index must be >= 0, got {self.index}")
        if self.page_no is not None and self.page_no < 1:
            raise ValueError(f"page_no must be >= 1, got {self.page_no}")


class ParseError(BaseModel):
    """Structured parse error payload for audit and retry classification."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    """Unified parsing result for all document types."""

    file_path: str
    file_type: Literal["txt", "md", "docx", "pdf", "unsupported"]
    raw_text: str
    title: str | None = None
    parse_status: Literal["success", "partial", "failed"] = "success"
    error_info: str | None = None
    error: ParseError | None = None
    paragraphs: list[Paragraph] = Field(default_factory=list)
    page_count: int | None = None
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def _sync_error_fields(self) -> "ParsedDocument":
        if self.error is None and self.error_info:
            default_code = "partial_parse" if self.parse_status == "partial" else "parse_failed"
            self.error = ParseError(code=default_code, message=self.error_info)
        elif self.error is not None and self.error_info is None:
            self.error_info = self.error.message
        return self


def finalize_parsed_document(
    result: ParsedDocument,
    *,
    parser_name: str,
) -> ParsedDocument:
    """Normalize parser output and enforce the shared extractability contract.

    S2's authoritative parse state must come from the parsed content itself,
    not from downstream index/chunk consumers guessing what an empty payload
    means. A document with no extractable normalized text is therefore a
    failed parse, even if the file exists and the low-level parser did not
    raise.
    """

    if result.parse_status == "failed":
        return result

    if result.error is None and result.error_info:
        error_code = "partial_parse" if result.parse_status == "partial" else "parse_failed"
        result.error = ParseError(
            code=error_code,
            message=result.error_info,
            details={"parser": parser_name},
        )

    if result.title is not None:
        result.title = normalize_text(result.title)
    result.metadata = result.metadata.normalized_with(normalize_text)

    if result.raw_text:
        for para in result.paragraphs:
            para.text = normalize_text(para.text)
            if para.heading_path is not None:
                para.heading_path = normalize_text(para.heading_path)
        if result.paragraphs:
            parts = [p.text for p in result.paragraphs]
            result.raw_text = "\n".join(parts)
            offset = 0
            for para in result.paragraphs:
                para.start_char = offset
                para.end_char = offset + len(para.text)
                offset = para.end_char + 1
        else:
            result.raw_text = normalize_text(result.raw_text)

    if result.raw_text.strip():
        return result

    error_message = "no extractable text"
    error_details: dict[str, Any] = {"parser": parser_name}
    if result.error is not None:
        error_details["upstream_code"] = result.error.code
        if result.error.details:
            error_details["upstream_details"] = result.error.details
    if result.error_info:
        error_message = f"{error_message}; {result.error_info}"
    return ParsedDocument(
        file_path=result.file_path,
        file_type=result.file_type,
        raw_text="",
        title=result.title,
        parse_status="failed",
        error_info=error_message,
        error=ParseError(
            code="no_extractable_text",
            message=error_message,
            details=error_details,
        ),
        paragraphs=[],
        page_count=result.page_count,
        metadata=result.metadata,
    )


class BaseParser(ABC):
    """Abstract base class for document parsers.

    **Important**: external callers should use ``ParserRegistry.parse()``
    rather than calling individual parsers directly. The registry provides
    failure isolation and format routing; the parser base class owns the
    shared parse-finalization contract.
    """

    def parse(self, file_path: Path) -> ParsedDocument:
        """Parse a file and return a finalized ParsedDocument."""
        return finalize_parsed_document(
            self._parse_raw(file_path),
            parser_name=self.__class__.__name__,
        )

    @abstractmethod
    def _parse_raw(self, file_path: Path) -> ParsedDocument:
        """Extract the raw ParsedDocument before shared finalization."""

    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """Return list of supported file extensions (e.g. ['.txt'])."""


class ParserRegistry:
    """Registry that maps file extensions to parsers.

    The ``parse()`` convenience method guarantees no exception is raised,
    making it safe for batch processing.
    """

    def __init__(self) -> None:
        self._parsers: dict[str, BaseParser] = {}

    def register(self, parser: BaseParser) -> None:
        """Register a parser for its supported extensions."""
        for ext in parser.supported_extensions():
            ext_lower = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            self._parsers[ext_lower] = parser

    def get_parser(self, file_path: str | Path) -> BaseParser | None:
        """Return the parser for *file_path*, or ``None``."""
        ext = Path(file_path).suffix.lower()
        return self._parsers.get(ext)

    def is_supported(self, file_path: str | Path) -> bool:
        """Check whether the file extension is supported."""
        return self.get_parser(file_path) is not None

    # ------------------------------------------------------------------
    # Convenience method – never raises
    # ------------------------------------------------------------------

    def parse(self, file_path: Path) -> ParsedDocument:
        """Parse *file_path*, returning a failed ``ParsedDocument`` on any error."""
        file_path = Path(file_path)
        ext = file_path.suffix.lower()

        # Determine file_type for the result
        ext_to_type: dict[str, Literal["txt", "md", "docx", "pdf", "unsupported"]] = {
            ".txt": "txt",
            ".md": "md",
            ".docx": "docx",
            ".pdf": "pdf",
        }
        file_type = ext_to_type.get(ext, "unsupported")

        def _failed(error_code: str, error_info: str, **details: object) -> ParsedDocument:
            return ParsedDocument(
                file_path=str(file_path),
                file_type=file_type,
                raw_text="",
                parse_status="failed",
                error_info=error_info,
                error=ParseError(
                    code=error_code,
                    message=error_info,
                    details={k: v for k, v in details.items() if v is not None},
                ),
            )

        # Unsupported format
        parser = self.get_parser(file_path)
        if parser is None:
            logger.warning("Unsupported format: %s", ext)
            return _failed("unsupported_format", f"unsupported format: {ext}", extension=ext)

        try:
            file_path.stat()
        except PermissionError:
            return _failed("permission_denied", "permission denied", operation="stat")
        except OSError as exc:
            return _failed(
                "io_error",
                str(exc),
                operation="stat",
                errno=exc.errno,
                exception_type=type(exc).__name__,
            )

        # Delegate to parser
        try:
            result = parser.parse(file_path)
        except ParseUnsupportedError as exc:
            logger.warning("Parse error for %s: %s", file_path, exc)
            return _failed(
                "parse_unsupported",
                str(exc),
                parser=parser.__class__.__name__,
            )
        except ParseFailedError as exc:
            logger.warning("Parse error for %s: %s", file_path, exc)
            return _failed(
                "parse_failed",
                str(exc),
                parser=parser.__class__.__name__,
            )
        except PermissionError:
            return _failed(
                "permission_denied",
                "permission denied",
                operation="parse",
                parser=parser.__class__.__name__,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error parsing %s", file_path)
            return _failed(
                "unexpected_error",
                f"unexpected error: {exc}",
                parser=parser.__class__.__name__,
                exception_type=type(exc).__name__,
            )
        return result

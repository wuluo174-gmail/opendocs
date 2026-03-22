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


class BaseParser(ABC):
    """Abstract base class for document parsers.

    **Important**: external callers should use ``ParserRegistry.parse()``
    rather than calling individual parsers directly.  The registry applies
    text normalization and failure isolation that individual parsers do not.
    """

    @abstractmethod
    def parse(self, file_path: Path) -> ParsedDocument:
        """Parse a file and return a ParsedDocument."""

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

        # Acceptance TC-002 treats empty files as problematic inputs that
        # must surface in the failure bucket, not as successful parses.
        try:
            if file_path.stat().st_size == 0:
                return _failed("empty_file", "empty file")
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

        if result.error is None and result.error_info:
            error_code = "partial_parse" if result.parse_status == "partial" else "parse_failed"
            result.error = ParseError(
                code=error_code,
                message=result.error_info,
                details={"parser": parser.__class__.__name__},
            )

        # Apply text normalization (NFC, fullwidth→halfwidth, whitespace)
        # then recompute offsets so they match the normalized raw_text.
        #
        # NOTE (ADR-0010): After normalization, raw_text and char offsets
        # correspond to the *normalized* text, NOT the original file bytes.
        # If a future stage (e.g. FR-015 evidence viewer) needs to jump to
        # the exact position in the original file, an additional original-
        # offset mapping will be required.  Within S2 the offsets are
        # internally consistent (tested in TestNormalizationOffsetIntegrity).
        if result.parse_status != "failed":
            if result.title is not None:
                result.title = normalize_text(result.title)
            result.metadata = result.metadata.normalized_with(normalize_text)

        if result.parse_status != "failed" and result.raw_text:
            # Normalize each paragraph text first
            for para in result.paragraphs:
                para.text = normalize_text(para.text)
                if para.heading_path is not None:
                    para.heading_path = normalize_text(para.heading_path)
            # Rebuild raw_text from normalized paragraphs and recompute offsets
            if result.paragraphs:
                parts = [p.text for p in result.paragraphs]
                result.raw_text = "\n".join(parts)
                offset = 0
                for para in result.paragraphs:
                    para.start_char = offset
                    para.end_char = offset + len(para.text)
                    offset = para.end_char + 1  # +1 for \n separator
            else:
                result.raw_text = normalize_text(result.raw_text)

        return result

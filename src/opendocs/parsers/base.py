"""ParsedDocument model, Paragraph dataclass, BaseParser ABC, and ParserRegistry."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from opendocs.exceptions import ParseFailedError, ParseUnsupportedError

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


class ParsedDocument(BaseModel):
    """Unified parsing result for all document types."""

    file_path: str
    file_type: Literal["txt", "md", "docx", "pdf"]
    raw_text: str
    title: str | None = None
    parse_status: Literal["success", "partial", "failed"] = "success"
    error_info: str | None = None
    paragraphs: list[Paragraph] = []
    page_count: int | None = None

    model_config = {"arbitrary_types_allowed": True}


class BaseParser(ABC):
    """Abstract base class for document parsers."""

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
        ext_to_type: dict[str, Literal["txt", "md", "docx", "pdf"]] = {
            ".txt": "txt",
            ".md": "md",
            ".docx": "docx",
            ".pdf": "pdf",
        }
        file_type = ext_to_type.get(ext, "txt")

        def _failed(error_info: str) -> ParsedDocument:
            return ParsedDocument(
                file_path=str(file_path),
                file_type=file_type,
                raw_text="",
                parse_status="failed",
                error_info=error_info,
            )

        # Unsupported format
        parser = self.get_parser(file_path)
        if parser is None:
            logger.warning("Unsupported format: %s", ext)
            return _failed(f"unsupported format: {ext}")

        # Empty file
        try:
            if file_path.stat().st_size == 0:
                return _failed("empty file")
        except PermissionError:
            return _failed("permission denied")
        except OSError as exc:
            return _failed(str(exc))

        # Delegate to parser
        try:
            return parser.parse(file_path)
        except (ParseUnsupportedError, ParseFailedError) as exc:
            logger.warning("Parse error for %s: %s", file_path, exc)
            return _failed(str(exc))
        except PermissionError:
            return _failed("permission denied")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error parsing %s", file_path)
            return _failed(f"unexpected error: {exc}")

"""OpenDocs parsers – unified document parsing."""

from opendocs.domain.document_metadata import DocumentMetadata
from opendocs.parsers.base import BaseParser, Paragraph, ParsedDocument, ParseError, ParserRegistry
from opendocs.parsers.docx_parser import DocxParser
from opendocs.parsers.md_parser import MdParser
from opendocs.parsers.normalization import normalize_text
from opendocs.parsers.pdf_parser import PdfParser
from opendocs.parsers.txt_parser import TxtParser

__all__ = [
    "BaseParser",
    "Paragraph",
    "DocumentMetadata",
    "ParseError",
    "ParsedDocument",
    "ParserRegistry",
    "TxtParser",
    "MdParser",
    "DocxParser",
    "PdfParser",
    "create_default_registry",
    "normalize_text",
]


def create_default_registry() -> ParserRegistry:
    """Create a registry with all built-in parsers registered."""
    registry = ParserRegistry()
    registry.register(TxtParser())
    registry.register(MdParser())
    registry.register(DocxParser())
    registry.register(PdfParser())
    return registry

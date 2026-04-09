"""Application service exports."""

from .file_operation_service import FileOperationService
from .memory_service import MemoryService

# Lazy imports to avoid circular dependency:
# index_builder → _audit_helpers → app.__init__ → index_service → index_builder


def __getattr__(name: str) -> object:
    if name == "OpenDocsRuntime":
        from .runtime import OpenDocsRuntime

        return OpenDocsRuntime
    if name == "IndexService":
        from .index_service import IndexService

        return IndexService
    if name == "SourceService":
        from .source_service import SourceService

        return SourceService
    if name == "SearchService":
        from .search_service import SearchService

        return SearchService
    if name == "QAService":
        from .qa_service import QAService

        return QAService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "FileOperationService",
    "IndexService",
    "MemoryService",
    "OpenDocsRuntime",
    "QAService",
    "SearchService",
    "SourceService",
]

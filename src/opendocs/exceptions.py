"""OpenDocs exception hierarchy."""

from __future__ import annotations


class OpenDocsError(Exception):
    """Base exception for all OpenDocs errors."""


class ConfigError(OpenDocsError):
    """Raised when configuration cannot be loaded or validated."""


class BootstrapError(OpenDocsError):
    """Raised when bootstrap/setup actions fail."""


class StorageError(OpenDocsError):
    """Raised when a storage operation fails (migration, query, integrity)."""


class SchemaCompatibilityError(StorageError):
    """Raised when a local SQLite DB no longer matches the current development schema."""


# ---------------------------------------------------------------------------
# 规范 §11.3 业务级错误码（供后续服务层按类型处理）
# ---------------------------------------------------------------------------


class SourceNotFoundError(OpenDocsError):
    """E_SOURCE_NOT_FOUND — 根目录不存在或不可读。"""


class SourceOverlapError(OpenDocsError):
    """E_SOURCE_OVERLAP — 根目录与现有活动来源发生所有权重叠。"""


class ParseUnsupportedError(OpenDocsError):
    """E_PARSE_UNSUPPORTED — 文件格式不支持解析。"""


class ParseFailedError(OpenDocsError):
    """E_PARSE_FAILED — 文件解析过程中发生错误。"""


class IndexCorruptedError(StorageError):
    """E_INDEX_CORRUPTED — 向量或 FTS 索引损坏，需重建。"""


class ArtifactBuildBusyError(StorageError):
    """E_ARTIFACT_BUILD_BUSY — 派生工件已有活动构建租约。"""


class RuntimeOwnershipError(OpenDocsError):
    """E_RUNTIME_OWNERSHIP_REQUIRED — 该操作必须由显式 runtime owner 驱动。"""


class RuntimeClosedError(OpenDocsError):
    """E_RUNTIME_CLOSED — runtime 已关闭，禁止继续复用其服务能力。"""


class EvidenceInsufficientError(OpenDocsError):
    """E_EVIDENCE_INSUFFICIENT — 证据不足，拒绝给出事实性回答。"""


class SearchExecutionError(OpenDocsError):
    """E_SEARCH_EXECUTION_FAILED — 搜索后端失败，调用方只能消费受控错误。"""

    def __init__(self, message: str, *, trace_id: str | None = None) -> None:
        super().__init__(message)
        self.trace_id = trace_id


class MemoryConflictError(OpenDocsError):
    """E_MEMORY_CONFLICT — 记忆与文档证据存在冲突。"""


class PlanNotApprovedError(OpenDocsError):
    """E_PLAN_NOT_APPROVED — 归档计划尚未经用户确认。"""


class FileOpFailedError(OpenDocsError):
    """E_FILE_OP_FAILED — 文件 move/rename/create 操作失败。"""


class RollbackPartialError(OpenDocsError):
    """E_ROLLBACK_PARTIAL — 批量回滚部分失败，存在未恢复文件。"""


class ProviderUnavailableError(OpenDocsError):
    """E_PROVIDER_UNAVAILABLE — 模型提供方不可用。"""


class DeleteNotAllowedError(OpenDocsError):
    """E_DELETE_NOT_ALLOWED — delete 默认禁用，需显式 allow_delete=True。"""

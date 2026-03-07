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


# ---------------------------------------------------------------------------
# 规范 §11.3 业务级错误码（供后续服务层按类型处理）
# ---------------------------------------------------------------------------


class SourceNotFoundError(OpenDocsError):
    """E_SOURCE_NOT_FOUND — 根目录不存在或不可读。"""


class ParseUnsupportedError(OpenDocsError):
    """E_PARSE_UNSUPPORTED — 文件格式不支持解析。"""


class ParseFailedError(OpenDocsError):
    """E_PARSE_FAILED — 文件解析过程中发生错误。"""


class IndexCorruptedError(StorageError):
    """E_INDEX_CORRUPTED — 向量或 FTS 索引损坏，需重建。"""


class EvidenceInsufficientError(OpenDocsError):
    """E_EVIDENCE_INSUFFICIENT — 证据不足，拒绝给出事实性回答。"""


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

"""SQLAlchemy ORM models for S1 storage baseline."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

from opendocs.utils.time import utcnow_naive

# Recommended operation values for AuditLogModel.operation (spec §8.1.7).
# S1 subset only — extend in later stages (e.g. summarize, rollback,
# provider_call, memory_read) as the corresponding features are built.
AUDIT_OPERATIONS = frozenset(
    {
        "move_execute",
        "rename_execute",
        "create_execute",
        "document_parse",
        "document_index",
        "chunk_create",
        "knowledge_extract",
        "memory_write",
        "search_query",
        "answer_generate",
    }
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def _uuid_check_sql(column: str) -> str:
    normalized = f"replace({column}, '-', '')"
    return (
        f"length({column}) = 36 AND "
        f"substr({column}, 9, 1) = '-' AND "
        f"substr({column}, 14, 1) = '-' AND "
        f"substr({column}, 19, 1) = '-' AND "
        f"substr({column}, 24, 1) = '-' AND "
        f"length({normalized}) = 32 AND "
        f"lower({column}) = {column} AND "
        f"NOT {normalized} GLOB '*[^0-9a-f]*'"
    )


def _sha256_check_sql(column: str) -> str:
    return (
        f"length({column}) = 64 AND lower({column}) = {column} AND NOT {column} GLOB '*[^0-9a-f]*'"
    )


class DocumentModel(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "file_type IN ('txt', 'md', 'docx', 'pdf')",
            name="ck_documents_file_type",
        ),
        CheckConstraint(
            "parse_status IN ('success', 'partial', 'failed')",
            name="ck_documents_parse_status",
        ),
        CheckConstraint(
            "sensitivity IN ('public', 'internal', 'sensitive')",
            name="ck_documents_sensitivity",
        ),
        CheckConstraint(_uuid_check_sql("doc_id"), name="ck_documents_doc_id_uuid"),
        CheckConstraint(
            _uuid_check_sql("source_root_id"),
            name="ck_documents_source_root_id_uuid",
        ),
        CheckConstraint(_sha256_check_sql("hash_sha256"), name="ck_documents_hash_sha256"),
        CheckConstraint("size_bytes >= 0", name="ck_documents_size_bytes_non_negative"),
    )

    doc_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_root_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # NOTE(S3): Spec §8.1.1 defines created_at/modified_at as *file-system* times.
    # The default=utcnow_naive is only a fallback; S3 scanner MUST explicitly set
    # these to os.path.getctime() / os.path.getmtime() from the actual file.
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    modified_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    parse_status: Mapped[str] = mapped_column(String(16), nullable=False, default="success")
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    sensitivity: Mapped[str] = mapped_column(String(16), nullable=False, default="internal")
    is_deleted_from_fs: Mapped[bool] = mapped_column(nullable=False, default=False)


class ChunkModel(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("doc_id", "chunk_index", name="uq_chunks_doc_index"),
        CheckConstraint("chunk_index >= 0", name="ck_chunks_chunk_index_non_negative"),
        CheckConstraint("char_end >= char_start", name="ck_chunks_char_range"),
        CheckConstraint(_uuid_check_sql("chunk_id"), name="ck_chunks_chunk_id_uuid"),
        CheckConstraint(_uuid_check_sql("doc_id"), name="ck_chunks_doc_id_uuid"),
    )

    chunk_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    doc_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.doc_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paragraph_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paragraph_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heading_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_key: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class KnowledgeItemModel(Base):
    __tablename__ = "knowledge_items"
    __table_args__ = (
        CheckConstraint(
            _uuid_check_sql("knowledge_id"),
            name="ck_knowledge_items_knowledge_id_uuid",
        ),
        CheckConstraint(_uuid_check_sql("doc_id"), name="ck_knowledge_items_doc_id_uuid"),
        CheckConstraint(_uuid_check_sql("chunk_id"), name="ck_knowledge_items_chunk_id_uuid"),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_knowledge_items_confidence_range",
        ),
    )

    knowledge_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    doc_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.doc_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chunks.chunk_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    entities_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    topics_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class RelationEdgeModel(Base):
    __tablename__ = "relation_edges"
    __table_args__ = (
        CheckConstraint(
            "src_type IN ('document', 'chunk', 'knowledge', 'memory', 'entity', 'topic')",
            name="ck_relation_edges_src_type",
        ),
        CheckConstraint(
            "dst_type IN ('document', 'chunk', 'knowledge', 'memory', 'entity', 'topic')",
            name="ck_relation_edges_dst_type",
        ),
        CheckConstraint(
            "relation_type IN ('related_to', 'mentions', 'derived_from', 'same_project')",
            name="ck_relation_edges_relation_type",
        ),
        CheckConstraint("weight >= 0.0", name="ck_relation_edges_weight_non_negative"),
        CheckConstraint(_uuid_check_sql("edge_id"), name="ck_relation_edges_edge_id_uuid"),
        CheckConstraint(
            "evidence_chunk_id IS NULL OR " + _uuid_check_sql("evidence_chunk_id"),
            name="ck_relation_edges_evidence_chunk_id_uuid",
        ),
        Index("idx_relation_edges_src", "src_type", "src_id"),
        Index("idx_relation_edges_dst", "dst_type", "dst_id"),
    )

    edge_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    src_type: Mapped[str] = mapped_column(String(32), nullable=False)
    src_id: Mapped[str] = mapped_column(Text, nullable=False)
    dst_type: Mapped[str] = mapped_column(String(32), nullable=False)
    dst_id: Mapped[str] = mapped_column(Text, nullable=False)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    evidence_chunk_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("chunks.chunk_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class MemoryItemModel(Base):
    __tablename__ = "memory_items"
    __table_args__ = (
        CheckConstraint("memory_type IN ('M0', 'M1', 'M2')", name="ck_memory_items_memory_type"),
        CheckConstraint(
            "scope_type IN ('session', 'task', 'user')",
            name="ck_memory_items_scope_type",
        ),
        CheckConstraint(
            "status IN ('active', 'expired', 'disabled')",
            name="ck_memory_items_status",
        ),
        CheckConstraint(
            "importance >= 0.0 AND importance <= 1.0",
            name="ck_memory_items_importance_range",
        ),
        CheckConstraint(
            "ttl_days IS NULL OR ttl_days >= 0",
            name="ck_memory_items_ttl_days_non_negative",
        ),
        UniqueConstraint(
            "memory_type",
            "scope_type",
            "scope_id",
            "key",
            name="uq_memory_items_scope_key",
        ),
        CheckConstraint(_uuid_check_sql("memory_id"), name="ck_memory_items_memory_id_uuid"),
    )

    memory_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    memory_type: Mapped[str] = mapped_column(String(8), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    ttl_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)


class FileOperationPlanModel(Base):
    __tablename__ = "file_operation_plans"
    __table_args__ = (
        CheckConstraint(
            "operation_type IN ('move', 'rename', 'create')",
            name="ck_file_operation_plans_operation_type",
        ),
        CheckConstraint(
            "status IN ('draft', 'approved', 'executed', 'rolled_back', 'failed')",
            name="ck_file_operation_plans_status",
        ),
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')",
            name="ck_file_operation_plans_risk_level",
        ),
        CheckConstraint(
            "item_count >= 0",
            name="ck_file_operation_plans_item_count_non_negative",
        ),
        CheckConstraint(_uuid_check_sql("plan_id"), name="ck_file_operation_plans_plan_id_uuid"),
    )

    plan_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    operation_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    preview_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("actor IN ('user', 'system', 'model')", name="ck_audit_logs_actor"),
        CheckConstraint("result IN ('success', 'failure')", name="ck_audit_logs_result"),
        CheckConstraint(
            "target_type IN ("
            "'document', 'plan', 'memory', 'answer', "
            "'source', 'search', 'provider_call', "
            "'generation', 'index_run', 'rollback')",
            name="ck_audit_logs_target_type",
        ),
        CheckConstraint(_uuid_check_sql("audit_id"), name="ck_audit_logs_audit_id_uuid"),
        CheckConstraint("length(trace_id) > 0", name="ck_audit_logs_trace_id_non_empty"),
        Index("idx_audit_logs_target", "target_type", "target_id"),
    )

    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
        index=True,
    )
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    detail_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

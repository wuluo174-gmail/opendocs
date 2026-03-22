"""Constraint tests for S1 ORM models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opendocs.domain.models import (
    AuditLogModel,
    Base,
    ChunkModel,
    DocumentModel,
    FileOperationPlanModel,
    KnowledgeItemModel,
    MemoryItemModel,
    RelationEdgeModel,
    ScanRunModel,
    SourceRootModel,
)
from opendocs.utils.path_facts import derive_directory_facts


def _directory_fields(path: str, relative_path: str) -> dict[str, str]:
    directory_path, relative_directory_path = derive_directory_facts(path, relative_path)
    return {
        "directory_path": directory_path,
        "relative_directory_path": relative_directory_path,
    }


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys = ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


@pytest.fixture()
def source_root_id(session: Session) -> str:
    now = datetime.now(UTC).replace(tzinfo=None)
    source_root = SourceRootModel(
        source_root_id=str(uuid.uuid4()),
        path="C:/demo",
        label="test source",
        exclude_rules_json={},
        recursive=True,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    session.add(source_root)
    session.flush()
    return source_root.source_root_id


def test_document_file_type_check_constraint(session: Session, source_root_id: str) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    document = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path="C:/demo/a.bin",
        relative_path="a.bin",
        **_directory_fields("C:/demo/a.bin", "a.bin"),
        source_root_id=source_root_id,
        source_path="C:/demo/a.bin",
        hash_sha256="a" * 64,
        title="bad type",
        file_type="bin",
        size_bytes=10,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
    )
    session.add(document)
    with pytest.raises(IntegrityError):
        session.commit()


def test_document_doc_id_must_be_uuid(session: Session, source_root_id: str) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    document = DocumentModel(
        doc_id="not-a-uuid",
        path="C:/demo/invalid-id.md",
        relative_path="invalid-id.md",
        **_directory_fields("C:/demo/invalid-id.md", "invalid-id.md"),
        source_root_id=source_root_id,
        source_path="C:/demo/invalid-id.md",
        hash_sha256="a" * 64,
        title="bad id",
        file_type="md",
        size_bytes=10,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
    )
    session.add(document)
    with pytest.raises(IntegrityError):
        session.commit()


def test_document_hash_must_be_lower_hex_sha256(session: Session, source_root_id: str) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    document = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path="C:/demo/invalid-hash.md",
        relative_path="invalid-hash.md",
        **_directory_fields("C:/demo/invalid-hash.md", "invalid-hash.md"),
        source_root_id=source_root_id,
        source_path="C:/demo/invalid-hash.md",
        hash_sha256="G" * 64,
        title="bad hash",
        file_type="md",
        size_bytes=10,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
    )
    session.add(document)
    with pytest.raises(IntegrityError):
        session.commit()


def test_document_file_identity_must_be_unique(session: Session, source_root_id: str) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    file_identity = "7:11"
    first = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path="C:/demo/identity-1.md",
        relative_path="identity-1.md",
        **_directory_fields("C:/demo/identity-1.md", "identity-1.md"),
        file_identity=file_identity,
        source_root_id=source_root_id,
        source_path="C:/demo/identity-1.md",
        hash_sha256="a" * 64,
        title="identity one",
        file_type="md",
        size_bytes=10,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
    )
    second = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path="C:/demo/identity-2.md",
        relative_path="identity-2.md",
        **_directory_fields("C:/demo/identity-2.md", "identity-2.md"),
        file_identity=file_identity,
        source_root_id=source_root_id,
        source_path="C:/demo/identity-2.md",
        hash_sha256="b" * 64,
        title="identity two",
        file_type="md",
        size_bytes=10,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
    )
    session.add(first)
    session.commit()
    session.add(second)
    with pytest.raises(IntegrityError):
        session.commit()


def test_document_path_must_be_unique_only_for_active_rows(
    session: Session, source_root_id: str
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    shared_path = "C:/demo/reused.md"
    first = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path=shared_path,
        relative_path="reused.md",
        **_directory_fields(shared_path, "reused.md"),
        source_root_id=source_root_id,
        source_path=shared_path,
        hash_sha256="c" * 64,
        title="deleted lineage",
        file_type="md",
        size_bytes=10,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
        is_deleted_from_fs=True,
    )
    second = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path=shared_path,
        relative_path="reused.md",
        **_directory_fields(shared_path, "reused.md"),
        source_root_id=source_root_id,
        source_path=shared_path,
        hash_sha256="d" * 64,
        title="active lineage",
        file_type="md",
        size_bytes=10,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
    )
    duplicate_active = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path=shared_path,
        relative_path="reused.md",
        **_directory_fields(shared_path, "reused.md"),
        source_root_id=source_root_id,
        source_path=shared_path,
        hash_sha256="e" * 64,
        title="duplicate active",
        file_type="md",
        size_bytes=10,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
    )

    session.add(first)
    session.add(second)
    session.commit()

    session.add(duplicate_active)
    with pytest.raises(IntegrityError):
        session.commit()


def test_document_failed_status_may_omit_hash(session: Session, source_root_id: str) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    document = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path="C:/demo/hash-missing-failed.md",
        relative_path="hash-missing-failed.md",
        **_directory_fields("C:/demo/hash-missing-failed.md", "hash-missing-failed.md"),
        source_root_id=source_root_id,
        source_path="C:/demo/hash-missing-failed.md",
        hash_sha256=None,
        title="failed without hash",
        file_type="md",
        size_bytes=10,
        created_at=now,
        modified_at=now,
        parse_status="failed",
        sensitivity="internal",
    )
    session.add(document)
    session.commit()


def test_document_non_failed_status_requires_hash(session: Session, source_root_id: str) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    document = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path="C:/demo/hash-missing-success.md",
        relative_path="hash-missing-success.md",
        **_directory_fields("C:/demo/hash-missing-success.md", "hash-missing-success.md"),
        source_root_id=source_root_id,
        source_path="C:/demo/hash-missing-success.md",
        hash_sha256=None,
        title="success without hash",
        file_type="md",
        size_bytes=10,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
    )
    session.add(document)
    with pytest.raises(IntegrityError):
        session.commit()


def test_document_requires_existing_source_root(session: Session) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    document = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path="C:/demo/missing-source-root.md",
        relative_path="missing-source-root.md",
        **_directory_fields("C:/demo/missing-source-root.md", "missing-source-root.md"),
        source_root_id=str(uuid.uuid4()),
        source_path="C:/demo/missing-source-root.md",
        hash_sha256="a" * 64,
        title="missing source root",
        file_type="md",
        size_bytes=10,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
    )
    session.add(document)
    with pytest.raises(IntegrityError):
        session.commit()


def test_scan_run_requires_existing_source_root(session: Session) -> None:
    scan_run = ScanRunModel(
        scan_run_id=str(uuid.uuid4()),
        source_root_id=str(uuid.uuid4()),
        started_at=datetime.now(UTC).replace(tzinfo=None),
        trace_id="trace-scan-run",
    )
    session.add(scan_run)
    with pytest.raises(IntegrityError):
        session.commit()


def test_source_root_default_sensitivity_check_constraint(session: Session) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    source_root = SourceRootModel(
        source_root_id=str(uuid.uuid4()),
        path="C:/demo/source-with-bad-defaults",
        label="bad defaults",
        exclude_rules_json={},
        default_category="project",
        default_tags_json=["roadmap"],
        default_sensitivity="secret",
        recursive=True,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    session.add(source_root)
    with pytest.raises(IntegrityError):
        session.commit()


def test_memory_type_check_constraint(session: Session) -> None:
    memory = MemoryItemModel(
        memory_id=str(uuid.uuid4()),
        memory_type="M9",
        scope_type="task",
        scope_id="task-1",
        key="key",
        content="value",
        importance=0.8,
        status="active",
    )
    session.add(memory)
    with pytest.raises(IntegrityError):
        session.commit()


def test_audit_target_type_check_constraint(session: Session) -> None:
    audit = AuditLogModel(
        audit_id=str(uuid.uuid4()),
        actor="system",
        operation="index",
        target_type="chunk",
        target_id="chunk-1",
        result="success",
        trace_id="trace-1",
    )
    session.add(audit)
    with pytest.raises(IntegrityError):
        session.commit()


def test_relation_edge_src_type_check_constraint(session: Session) -> None:
    relation = RelationEdgeModel(
        edge_id=str(uuid.uuid4()),
        src_type="invalid_type",
        src_id="doc-1",
        dst_type="document",
        dst_id="doc-2",
        relation_type="related_to",
        weight=1.0,
    )
    session.add(relation)
    with pytest.raises(IntegrityError):
        session.commit()


def test_relation_edge_dst_type_check_constraint(session: Session) -> None:
    relation = RelationEdgeModel(
        edge_id=str(uuid.uuid4()),
        src_type="document",
        src_id="doc-1",
        dst_type="invalid_type",
        dst_id="doc-2",
        relation_type="related_to",
        weight=1.0,
    )
    session.add(relation)
    with pytest.raises(IntegrityError):
        session.commit()


def test_relation_edge_relation_type_check_constraint(session: Session) -> None:
    relation = RelationEdgeModel(
        edge_id=str(uuid.uuid4()),
        src_type="document",
        src_id="doc-1",
        dst_type="document",
        dst_id="doc-2",
        relation_type="invalid",
        weight=1.0,
    )
    session.add(relation)
    with pytest.raises(IntegrityError):
        session.commit()


def test_knowledge_item_requires_existing_doc_and_chunk(session: Session) -> None:
    knowledge = KnowledgeItemModel(
        knowledge_id=str(uuid.uuid4()),
        doc_id=str(uuid.uuid4()),
        chunk_id=str(uuid.uuid4()),
        summary="missing references",
        entities_json=[],
        topics_json=[],
        confidence=0.7,
    )
    session.add(knowledge)
    with pytest.raises(IntegrityError):
        session.commit()


def test_chunk_char_end_must_not_be_less_than_char_start(
    session: Session,
    source_root_id: str,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    document = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path="C:/demo/chunk-invalid.md",
        relative_path="chunk-invalid.md",
        **_directory_fields("C:/demo/chunk-invalid.md", "chunk-invalid.md"),
        source_root_id=source_root_id,
        source_path="C:/demo/chunk-invalid.md",
        hash_sha256="b" * 64,
        title="chunk invalid",
        file_type="md",
        size_bytes=10,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
    )
    session.add(document)
    session.flush()
    chunk = ChunkModel(
        chunk_id=str(uuid.uuid4()),
        doc_id=document.doc_id,
        chunk_index=0,
        text="demo",
        char_start=10,
        char_end=5,
    )
    session.add(chunk)
    with pytest.raises(IntegrityError):
        session.commit()


def test_memory_ttl_days_must_be_non_negative(session: Session) -> None:
    memory = MemoryItemModel(
        memory_id=str(uuid.uuid4()),
        memory_type="M1",
        scope_type="task",
        scope_id="task-1",
        key="deadline",
        content="soon",
        importance=0.8,
        status="active",
        ttl_days=-1,
    )
    session.add(memory)
    with pytest.raises(IntegrityError):
        session.commit()


def test_document_size_bytes_must_be_non_negative(session: Session, source_root_id: str) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    document = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path="C:/demo/negative-size.md",
        relative_path="negative-size.md",
        **_directory_fields("C:/demo/negative-size.md", "negative-size.md"),
        source_root_id=source_root_id,
        source_path="C:/demo/negative-size.md",
        hash_sha256="a" * 64,
        title="negative size",
        file_type="md",
        size_bytes=-1,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
    )
    session.add(document)
    with pytest.raises(IntegrityError):
        session.commit()


def test_memory_importance_must_be_in_range(session: Session) -> None:
    memory = MemoryItemModel(
        memory_id=str(uuid.uuid4()),
        memory_type="M1",
        scope_type="task",
        scope_id="task-1",
        key="oob-importance",
        content="test",
        importance=1.5,
        status="active",
    )
    session.add(memory)
    with pytest.raises(IntegrityError):
        session.commit()


def test_relation_edge_weight_must_be_non_negative(session: Session) -> None:
    relation = RelationEdgeModel(
        edge_id=str(uuid.uuid4()),
        src_type="document",
        src_id="doc-1",
        dst_type="document",
        dst_id="doc-2",
        relation_type="related_to",
        weight=-0.5,
    )
    session.add(relation)
    with pytest.raises(IntegrityError):
        session.commit()


def test_audit_trace_id_must_be_non_empty(session: Session) -> None:
    audit = AuditLogModel(
        audit_id=str(uuid.uuid4()),
        actor="system",
        operation="index",
        target_type="document",
        target_id="doc-1",
        result="success",
        trace_id="",
    )
    session.add(audit)
    with pytest.raises(IntegrityError):
        session.commit()


def test_chunk_index_must_be_non_negative(session: Session, source_root_id: str) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    document = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path="C:/demo/chunk-neg-idx.md",
        relative_path="chunk-neg-idx.md",
        **_directory_fields("C:/demo/chunk-neg-idx.md", "chunk-neg-idx.md"),
        source_root_id=source_root_id,
        source_path="C:/demo/chunk-neg-idx.md",
        hash_sha256="c" * 64,
        title="chunk neg index",
        file_type="md",
        size_bytes=10,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
    )
    session.add(document)
    session.flush()
    chunk = ChunkModel(
        chunk_id=str(uuid.uuid4()),
        doc_id=document.doc_id,
        chunk_index=-1,
        text="demo",
        char_start=0,
        char_end=4,
    )
    session.add(chunk)
    with pytest.raises(IntegrityError):
        session.commit()


def test_plan_item_count_must_be_non_negative(session: Session) -> None:
    plan = FileOperationPlanModel(
        plan_id=str(uuid.uuid4()),
        operation_type="move",
        status="draft",
        item_count=-1,
        risk_level="low",
        preview_json={"items": []},
    )
    session.add(plan)
    with pytest.raises(IntegrityError):
        session.commit()

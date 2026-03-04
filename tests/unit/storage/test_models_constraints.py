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
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys = ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def test_document_file_type_check_constraint(session: Session) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    document = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path="C:/demo/a.bin",
        relative_path="a.bin",
        source_root_id=str(uuid.uuid4()),
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


def test_document_doc_id_must_be_uuid(session: Session) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    document = DocumentModel(
        doc_id="not-a-uuid",
        path="C:/demo/invalid-id.md",
        relative_path="invalid-id.md",
        source_root_id=str(uuid.uuid4()),
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


def test_document_hash_must_be_lower_hex_sha256(session: Session) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    document = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path="C:/demo/invalid-hash.md",
        relative_path="invalid-hash.md",
        source_root_id=str(uuid.uuid4()),
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


def test_chunk_char_end_must_not_be_less_than_char_start(session: Session) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    document = DocumentModel(
        doc_id=str(uuid.uuid4()),
        path="C:/demo/chunk-invalid.md",
        relative_path="chunk-invalid.md",
        source_root_id=str(uuid.uuid4()),
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

"""CRUD tests for storage repositories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from opendocs.domain.models import (
    AuditLogModel,
    ChunkModel,
    DocumentModel,
    FileOperationPlanModel,
    MemoryItemModel,
)
from opendocs.storage.repositories import (
    AuditRepository,
    ChunkRepository,
    DocumentRepository,
    MemoryRepository,
    PlanRepository,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _new_document(path: str) -> DocumentModel:
    now = _now()
    return DocumentModel(
        doc_id=str(uuid.uuid4()),
        path=path,
        relative_path=path.split("/")[-1],
        source_root_id=str(uuid.uuid4()),
        source_path=path,
        hash_sha256="b" * 64,
        title="Document",
        file_type="md",
        size_bytes=128,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
    )


def test_document_repository_crud(engine: Engine) -> None:
    with Session(engine) as session:
        repository = DocumentRepository(session)
        document = _new_document("C:/docs/doc.md")

        repository.create(document)
        session.commit()

        fetched = repository.get_by_path("C:/docs/doc.md")
        assert fetched is not None
        assert fetched.doc_id == document.doc_id

        updated = repository.update_title(document.doc_id, "Updated Title")
        session.commit()
        assert updated is True
        assert repository.get_by_id(document.doc_id).title == "Updated Title"

        deleted = repository.delete(document.doc_id)
        session.commit()
        assert deleted is True
        assert repository.get_by_id(document.doc_id) is None


def test_chunk_repository_crud(engine: Engine) -> None:
    with Session(engine) as session:
        document = _new_document("C:/docs/chunk.md")
        DocumentRepository(session).create(document)
        session.flush()

        repository = ChunkRepository(session)
        chunk = ChunkModel(
            chunk_id=str(uuid.uuid4()),
            doc_id=document.doc_id,
            chunk_index=0,
            text="chunk text",
            char_start=0,
            char_end=10,
        )
        repository.create(chunk)
        session.commit()

        chunks = repository.list_by_document(document.doc_id)
        assert len(chunks) == 1
        assert chunks[0].chunk_id == chunk.chunk_id

        assert repository.update_text(
            chunk.chunk_id,
            text="updated chunk text",
            char_end=len("updated chunk text"),
        ) is True
        session.commit()
        refreshed = repository.get_by_id(chunk.chunk_id)
        assert refreshed is not None
        assert refreshed.text == "updated chunk text"
        assert refreshed.char_end == len("updated chunk text")

        assert repository.delete(chunk.chunk_id) is True
        session.commit()
        assert repository.get_by_id(chunk.chunk_id) is None


def test_memory_repository_crud(engine: Engine) -> None:
    with Session(engine) as session:
        repository = MemoryRepository(session)
        memory = MemoryItemModel(
            memory_id=str(uuid.uuid4()),
            memory_type="M1",
            scope_type="task",
            scope_id="task-001",
            key="deadline",
            content="2026-03-31",
            importance=0.9,
            status="active",
            updated_at=_now() - timedelta(seconds=5),
        )
        repository.create(memory)
        session.commit()

        fetched = repository.get_by_scope_key(
            memory_type="M1",
            scope_type="task",
            scope_id="task-001",
            key="deadline",
        )
        assert fetched is not None
        assert fetched.memory_id == memory.memory_id

        previous_updated_at = fetched.updated_at
        assert repository.update_status(memory.memory_id, "disabled") is True
        session.commit()
        updated = repository.get_by_id(memory.memory_id)
        assert updated.status == "disabled"
        assert updated.updated_at > previous_updated_at

        assert repository.delete(memory.memory_id) is True
        session.commit()
        assert repository.get_by_id(memory.memory_id) is None


def test_plan_repository_crud(engine: Engine) -> None:
    with Session(engine) as session:
        repository = PlanRepository(session)
        plan = FileOperationPlanModel(
            plan_id=str(uuid.uuid4()),
            operation_type="move",
            status="draft",
            item_count=2,
            risk_level="medium",
            preview_json={"items": [{"from": "a", "to": "b"}]},
        )
        repository.create(plan)
        session.commit()

        assert repository.get_by_id(plan.plan_id) is not None
        assert len(repository.list_by_status("draft")) == 1

        assert repository.update_status(plan.plan_id, "approved") is True
        session.commit()
        approved = repository.get_by_id(plan.plan_id)
        assert approved.status == "approved"
        assert approved.approved_at is not None

        assert repository.update_status(plan.plan_id, "executed") is True
        session.commit()
        executed = repository.get_by_id(plan.plan_id)
        assert executed.status == "executed"
        assert executed.executed_at is not None

        assert repository.delete(plan.plan_id) is True
        session.commit()
        assert repository.get_by_id(plan.plan_id) is None


def test_plan_repository_does_not_set_executed_at_when_not_executed(engine: Engine) -> None:
    with Session(engine) as session:
        repository = PlanRepository(session)
        plan = FileOperationPlanModel(
            plan_id=str(uuid.uuid4()),
            operation_type="move",
            status="draft",
            item_count=1,
            risk_level="low",
            preview_json={"items": [{"from": "a", "to": "b"}]},
        )
        repository.create(plan)
        session.commit()

        candidate_executed_at = _now()
        assert repository.update_status(
            plan.plan_id,
            "approved",
            executed_at=candidate_executed_at,
        ) is True
        session.commit()

        refreshed = repository.get_by_id(plan.plan_id)
        assert refreshed.status == "approved"
        assert refreshed.executed_at is None


def test_audit_repository_query(engine: Engine) -> None:
    with Session(engine) as session:
        repository = AuditRepository(session)
        now = _now()
        log1 = AuditLogModel(
            audit_id=str(uuid.uuid4()),
            timestamp=now - timedelta(minutes=5),
            actor="system",
            operation="index",
            target_type="document",
            target_id="doc-1",
            result="success",
            detail_json={"file_path": "C:/docs/a.md", "task_id": "task-1"},
            trace_id="trace-task-1",
        )
        log2 = AuditLogModel(
            audit_id=str(uuid.uuid4()),
            timestamp=now - timedelta(minutes=2),
            actor="user",
            operation="qa",
            target_type="answer",
            target_id="ans-1",
            result="success",
            detail_json={"file_path": "C:/docs/b.md", "task_id": "task-1"},
            trace_id="trace-task-1",
        )
        log3 = AuditLogModel(
            audit_id=str(uuid.uuid4()),
            timestamp=now - timedelta(minutes=10),
            actor="system",
            operation="index",
            target_type="document",
            target_id="doc-2",
            result="success",
            detail_json={"file_path": "C:/docs/a.md.bak", "task_id": "task-2"},
            trace_id="trace-task-2",
        )
        repository.create(log1)
        repository.create(log2)
        repository.create(log3)
        session.commit()

        assert repository.update_detail(
            log2.audit_id,
            detail_json={"file_path": "C:/docs/b.md", "task_id": "task-1", "updated": True},
            result="failure",
        ) is True
        session.commit()
        updated_log2 = repository.get_by_id(log2.audit_id)
        assert updated_log2 is not None
        assert updated_log2.result == "failure"
        assert updated_log2.detail_json["updated"] is True

        by_trace = repository.query(trace_id="trace-task-1")
        assert len(by_trace) == 2
        assert [entry.audit_id for entry in by_trace] == [log2.audit_id, log1.audit_id]

        by_file = repository.query(file_path="C:/docs/b.md")
        assert len(by_file) == 1
        assert by_file[0].audit_id == log2.audit_id

        by_task = repository.query(task_id="task-1")
        assert len(by_task) == 2
        assert [entry.audit_id for entry in by_task] == [log2.audit_id, log1.audit_id]

        exact_file = repository.query(file_path="C:/docs/a.md")
        assert len(exact_file) == 1
        assert exact_file[0].audit_id == log1.audit_id

        by_time = repository.query(start_time=now - timedelta(minutes=3), end_time=now)
        assert len(by_time) == 1
        assert by_time[0].audit_id == log2.audit_id

        assert repository.delete(log3.audit_id) is True
        session.commit()
        assert repository.get_by_id(log3.audit_id) is None

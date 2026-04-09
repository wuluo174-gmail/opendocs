"""Tests for the minimal memory service boundary."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from opendocs.app import MemoryService
from opendocs.domain.models import MemoryItemModel, TaskEventModel
from opendocs.exceptions import StorageError


def _task_event() -> TaskEventModel:
    return TaskEventModel(
        event_id=str(uuid.uuid4()),
        trace_id="trace-memory-service",
        stage_id="S1",
        task_type="seed_demo",
        scope_type="task",
        scope_id="scope-001",
        input_summary="input",
        output_summary="output",
        related_chunk_ids_json=[],
        evidence_refs_json=[],
    )


def _memory_item(memory_type: str, *, event_id: str) -> MemoryItemModel:
    return MemoryItemModel(
        memory_id=str(uuid.uuid4()),
        memory_type=memory_type,
        memory_kind="task_snapshot",
        scope_type="task" if memory_type != "M0" else "session",
        scope_id="scope-001",
        key="status",
        content="ready",
        source_event_ids_json=[event_id],
        evidence_refs_json=[],
        importance=0.5,
        confidence=0.8,
        status="active",
        review_window_days=30,
        user_confirmed_count=0,
        recall_count=0,
        decay_score=0.0,
        promotion_state="promoted",
        consolidated_from_json=[],
    )


def test_memory_service_rejects_m0_persistence(engine: Engine) -> None:
    with Session(engine) as session:
        service = MemoryService(session)
        task_event = _task_event()
        session.add(task_event)
        session.flush()

        with pytest.raises(StorageError, match="only M1/M2 memories may be persisted"):
            service.create(_memory_item("M0", event_id=task_event.event_id))

        session.rollback()
        rows = session.scalars(select(MemoryItemModel)).all()
        assert rows == []


def test_memory_service_persists_m1(engine: Engine) -> None:
    with Session(engine) as session:
        service = MemoryService(session)
        task_event = _task_event()
        session.add(task_event)
        session.flush()
        memory_item = _memory_item("M1", event_id=task_event.event_id)

        created = service.create(memory_item)
        session.commit()

        assert created.memory_id == memory_item.memory_id
        stored = session.get(MemoryItemModel, memory_item.memory_id)
        assert stored is not None
        assert stored.memory_type == "M1"

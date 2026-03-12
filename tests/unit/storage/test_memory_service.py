"""Tests for the minimal memory service boundary."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from opendocs.app import MemoryService
from opendocs.domain.models import MemoryItemModel
from opendocs.exceptions import StorageError


def _memory_item(memory_type: str) -> MemoryItemModel:
    return MemoryItemModel(
        memory_id=str(uuid.uuid4()),
        memory_type=memory_type,
        scope_type="task" if memory_type != "M0" else "session",
        scope_id="scope-001",
        key="status",
        content="ready",
        importance=0.5,
        status="active",
    )


def test_memory_service_rejects_m0_persistence(engine: Engine) -> None:
    with Session(engine) as session:
        service = MemoryService(session)

        with pytest.raises(StorageError, match="M0 session memory must not be persisted"):
            service.create(_memory_item("M0"))

        session.rollback()
        rows = session.scalars(select(MemoryItemModel)).all()
        assert rows == []


def test_memory_service_persists_m1(engine: Engine) -> None:
    with Session(engine) as session:
        service = MemoryService(session)
        memory_item = _memory_item("M1")

        created = service.create(memory_item)
        session.commit()

        assert created.memory_id == memory_item.memory_id
        stored = session.get(MemoryItemModel, memory_item.memory_id)
        assert stored is not None
        assert stored.memory_type == "M1"

"""Tests for the memory service — re-export and basic write/reject."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from opendocs.app import MemoryService
from opendocs.domain.models import MemoryItemModel
from opendocs.exceptions import StorageError


def test_memory_service_rejects_m0_persistence(engine: Engine) -> None:
    service = MemoryService(engine)
    with pytest.raises(StorageError, match="M0 session memory must not be persisted"):
        service.write(
            memory_type="M0",
            scope_type="session",
            scope_id="scope-001",
            key="status",
            content="ready",
            trace_id=str(uuid.uuid4()),
        )

    with Session(engine) as session:
        rows = session.query(MemoryItemModel).all()
        assert rows == []


def test_memory_service_persists_m1(engine: Engine) -> None:
    service = MemoryService(engine)
    trace = str(uuid.uuid4())

    created = service.write(
        memory_type="M1",
        scope_type="task",
        scope_id="scope-001",
        key="status",
        content="ready",
        trace_id=trace,
    )

    assert created.memory_type == "M1"

    with Session(engine) as session:
        stored = session.get(MemoryItemModel, created.memory_id)
        assert stored is not None
        assert stored.memory_type == "M1"

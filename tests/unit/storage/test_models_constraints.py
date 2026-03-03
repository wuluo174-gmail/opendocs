"""Constraint tests for S1 ORM models."""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opendocs.domain.models import Base, DocumentModel, MemoryItemModel


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
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

"""Shared fixtures for storage tests."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from opendocs.domain.models import SourceRootModel
from opendocs.storage.db import build_sqlite_engine, init_db
from opendocs.utils.time import utcnow_naive


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "opendocs.db"


@pytest.fixture()
def engine(db_path: Path) -> Engine:
    init_db(db_path)
    sqlite_engine = build_sqlite_engine(db_path)
    try:
        yield sqlite_engine
    finally:
        sqlite_engine.dispose()


def build_source_root(
    *,
    source_root_id: str | None = None,
    path: str | None = None,
) -> SourceRootModel:
    root_id = source_root_id or str(uuid.uuid4())
    root_path = path or f"/tmp/source-roots/{root_id}"
    now = utcnow_naive()
    return SourceRootModel(
        source_root_id=root_id,
        path=root_path,
        label="test source",
        exclude_rules_json={},
        recursive=True,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def add_source_root(
    session: Session,
    *,
    source_root_id: str | None = None,
    path: str | None = None,
) -> SourceRootModel:
    source_root = build_source_root(source_root_id=source_root_id, path=path)
    session.add(source_root)
    session.flush()
    return source_root

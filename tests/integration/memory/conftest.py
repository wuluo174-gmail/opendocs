"""Shared fixtures for memory integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine

from opendocs.config.settings import MemorySettings
from opendocs.memory.service import MemoryService
from opendocs.storage.db import build_sqlite_engine, init_db


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "opendocs.db"


@pytest.fixture()
def engine(db_path: Path) -> Engine:
    init_db(db_path)
    eng = build_sqlite_engine(db_path)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture()
def memory_service(engine: Engine) -> MemoryService:
    return MemoryService(engine, settings=MemorySettings(m1_ttl_days=30))

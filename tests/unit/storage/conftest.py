"""Shared fixtures for storage tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine

from opendocs.storage.db import build_sqlite_engine, init_db


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

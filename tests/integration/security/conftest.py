"""Security integration test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from opendocs.storage.db import build_sqlite_engine, init_db


@pytest.fixture()
def security_engine(tmp_path: Path) -> Engine:
    db_path = tmp_path / "security_test.db"
    init_db(db_path)
    return build_sqlite_engine(db_path)

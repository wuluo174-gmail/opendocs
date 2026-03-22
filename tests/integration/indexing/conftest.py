"""Shared fixtures for S3 integration tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from opendocs.app.index_service import IndexService
from opendocs.app.source_service import SourceService
from opendocs.storage.db import build_sqlite_engine, init_db
from opendocs.utils.logging import init_logging

# Static corpus committed to git
CORPUS_DIR = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "generated" / "corpus_main"
)


@pytest.fixture()
def work_dir(tmp_path: Path) -> Path:
    """Temporary working directory with logging initialized."""
    log_dir = tmp_path / "logs"
    init_logging(log_dir)
    return tmp_path


@pytest.fixture()
def db_path(work_dir: Path) -> Path:
    p = work_dir / "test.db"
    init_db(p)
    return p


@pytest.fixture()
def engine(db_path: Path) -> Engine:
    return build_sqlite_engine(db_path)


@pytest.fixture()
def hnsw_path(work_dir: Path) -> Path:
    p = work_dir / "index" / "hnsw" / "vectors.bin"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture()
def source_service(engine: Engine, hnsw_path: Path) -> SourceService:
    return SourceService(engine, hnsw_path=hnsw_path)


@pytest.fixture()
def index_service(engine: Engine, hnsw_path: Path) -> IndexService:
    return IndexService(engine, hnsw_path=hnsw_path)


@pytest.fixture()
def corpus_copy(tmp_path: Path) -> Path:
    """Copy of the static corpus so tests can add/delete files freely."""
    dest = tmp_path / "corpus"
    shutil.copytree(CORPUS_DIR, dest)
    return dest

"""Shared fixtures for S6 archive integration tests."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opendocs.app.archive_service import ArchiveService
from opendocs.domain.models import DocumentModel, SourceRootModel
from opendocs.storage.db import build_sqlite_engine, init_db, session_scope
from opendocs.utils.logging import init_logging
from opendocs.utils.time import utcnow_naive


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@pytest.fixture()
def work_dir(tmp_path: Path) -> Path:
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
def archive_dir(work_dir: Path) -> Path:
    p = work_dir / "archive_output"
    p.mkdir()
    return p


@pytest.fixture()
def source_files(work_dir: Path) -> list[Path]:
    """Create 5 real .md files with unique content."""
    src_dir = work_dir / "project-alpha"
    src_dir.mkdir()
    files: list[Path] = []
    for i in range(5):
        f = src_dir / f"doc_{i:03d}.md"
        f.write_text(f"# Document {i}\n\nUnique content {uuid.uuid4()}\n")
        files.append(f)
    return files


@pytest.fixture()
def seeded_docs(engine: Engine, source_files: list[Path]) -> list[str]:
    """Insert SourceRoot + DocumentModel rows, return doc_ids."""
    source_root_id = str(uuid.uuid4())
    source_path = str(source_files[0].parent.resolve())
    doc_ids: list[str] = []
    now = utcnow_naive()

    with session_scope(engine) as session:
        session.add(SourceRootModel(
            source_root_id=source_root_id,
            path=source_path,
            label="test",
            source_config_rev=1,
            created_at=now,
            updated_at=now,
        ))
        session.flush()

        for f in source_files:
            content = f.read_bytes()
            doc_id = str(uuid.uuid4())
            resolved = str(f.resolve())
            session.add(DocumentModel(
                doc_id=doc_id,
                path=resolved,
                relative_path=f.name,
                directory_path=str(f.parent.resolve()),
                relative_directory_path="project-alpha",
                source_root_id=source_root_id,
                source_path=source_path,
                source_config_rev=1,
                hash_sha256=_sha256(content),
                title=f.stem,
                file_type="md",
                size_bytes=len(content),
                created_at=now,
                modified_at=now,
                parse_status="success",
            ))
            doc_ids.append(doc_id)

    return doc_ids


@pytest.fixture()
def archive_service(engine: Engine) -> ArchiveService:
    return ArchiveService(engine)

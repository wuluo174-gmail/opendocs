"""Transaction boundary tests for session_scope."""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from opendocs.domain.models import DocumentModel
from opendocs.storage.db import session_scope


def _build_document(path: str) -> DocumentModel:
    now = datetime.now(UTC).replace(tzinfo=None)
    return DocumentModel(
        doc_id=str(uuid.uuid4()),
        path=path,
        relative_path=path.split("/")[-1],
        source_root_id=str(uuid.uuid4()),
        source_path=path,
        hash_sha256="a" * 64,
        title="demo",
        file_type="md",
        size_bytes=10,
        created_at=now,
        modified_at=now,
        parse_status="success",
        sensitivity="internal",
    )


def test_session_scope_commits_on_success(engine: Engine) -> None:
    with session_scope(engine) as session:
        session.add(_build_document("C:/docs/commit.md"))

    with Session(engine) as verify_session:
        rows = verify_session.scalars(select(DocumentModel)).all()
    assert len(rows) == 1


def test_session_scope_rolls_back_on_error(engine: Engine) -> None:
    with pytest.raises(RuntimeError):
        with session_scope(engine) as session:
            session.add(_build_document("C:/docs/rollback.md"))
            raise RuntimeError("force rollback")

    with Session(engine) as verify_session:
        rows = verify_session.scalars(select(DocumentModel)).all()
    assert rows == []

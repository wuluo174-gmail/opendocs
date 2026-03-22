"""Transaction boundary tests for session_scope."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from opendocs.domain.models import DocumentModel, SourceRootModel
from opendocs.storage.db import session_scope
from opendocs.utils.path_facts import derive_directory_facts


def _add_source_root(session: Session, *, path: str) -> SourceRootModel:
    now = datetime.now(UTC).replace(tzinfo=None)
    source_root = SourceRootModel(
        source_root_id=str(uuid.uuid4()),
        path=path,
        label="rollback test source",
        exclude_rules_json={},
        recursive=True,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    session.add(source_root)
    session.flush()
    return source_root


def _build_document(path: str, *, source_root_id: str) -> DocumentModel:
    now = datetime.now(UTC).replace(tzinfo=None)
    directory_path, relative_directory_path = derive_directory_facts(
        path,
        path.split("/")[-1],
    )
    return DocumentModel(
        doc_id=str(uuid.uuid4()),
        path=path,
        relative_path=path.split("/")[-1],
        directory_path=directory_path,
        relative_directory_path=relative_directory_path,
        source_root_id=source_root_id,
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
        source_root = _add_source_root(session, path="C:/docs")
        session.add(
            _build_document(
                "C:/docs/commit.md",
                source_root_id=source_root.source_root_id,
            )
        )

    with Session(engine) as verify_session:
        rows = verify_session.scalars(select(DocumentModel)).all()
    assert len(rows) == 1


def test_session_scope_rolls_back_on_error(engine: Engine) -> None:
    with pytest.raises(RuntimeError):
        with session_scope(engine) as session:
            source_root = _add_source_root(session, path="C:/docs")
            session.add(
                _build_document(
                    "C:/docs/rollback.md",
                    source_root_id=source_root.source_root_id,
                )
            )
            raise RuntimeError("force rollback")

    with Session(engine) as verify_session:
        rows = verify_session.scalars(select(DocumentModel)).all()
    assert rows == []

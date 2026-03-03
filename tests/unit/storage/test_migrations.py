"""Migration tests for S1 storage baseline."""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from opendocs.storage.db import init_db, migrate


def _list_tables(db_path: Path) -> set[str]:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        connection.close()


def test_init_db_creates_core_tables(db_path: Path) -> None:
    init_db(db_path)
    tables = _list_tables(db_path)
    assert "schema_migrations" in tables
    assert "documents" in tables
    assert "chunks" in tables
    assert "memory_items" in tables
    assert "file_operation_plans" in tables
    assert "audit_logs" in tables
    assert "chunk_fts" in tables


def test_migrate_is_idempotent(db_path: Path) -> None:
    first_applied = migrate(db_path)
    second_applied = migrate(db_path)
    assert first_applied == ["0001"]
    assert second_applied == []


def test_migration_version_recorded(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT version FROM schema_migrations WHERE version = '0001'"
        ).fetchone()
        assert row is not None
    finally:
        connection.close()


def test_migration_failure_is_atomic(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad_migration = db_path.parent / "0002_bad.sql"
    bad_migration.write_text(
        "CREATE TABLE bad_partial (id TEXT PRIMARY KEY);\n"
        "INSERT INTO not_exists(id) VALUES ('x');\n",
        encoding="utf-8",
    )

    from opendocs.storage import db as db_module

    monkeypatch.setattr(db_module, "_list_migration_files", lambda: [bad_migration])

    with pytest.raises(sqlite3.Error):
        db_module.migrate(db_path)

    connection = sqlite3.connect(db_path)
    try:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "bad_partial" not in table_names
    finally:
        connection.close()

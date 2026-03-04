"""Migration tests for S1 storage baseline."""

from __future__ import annotations

import sqlite3
from pathlib import Path

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
    assert "knowledge_items" in tables
    assert "relation_edges" in tables
    assert "memory_items" in tables
    assert "file_operation_plans" in tables
    assert "audit_logs" in tables
    assert "chunk_fts" in tables


def test_migrate_is_idempotent(db_path: Path) -> None:
    first_applied = migrate(db_path)
    second_applied = migrate(db_path)
    assert first_applied == ["0001", "0002", "0003"]
    assert second_applied == []


def test_migration_version_recorded(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        versions = {
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        }
        assert versions == {"0001", "0002", "0003"}
    finally:
        connection.close()


def test_migration_enforces_audit_target_type_constraint(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO audit_logs (
                    audit_id, timestamp, actor, operation, target_type,
                    target_id, result, detail_json, trace_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "audit-invalid",
                    "2026-03-03T00:00:00Z",
                    "system",
                    "index",
                    "chunk",
                    "chunk-1",
                    "success",
                    "{}",
                    "trace-invalid",
                ),
            )
    finally:
        connection.close()


def test_migration_enforces_relation_type_constraint(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO relation_edges (
                    edge_id, src_type, src_id, dst_type, dst_id, relation_type, weight
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "edge-invalid",
                    "document",
                    "doc-1",
                    "document",
                    "doc-2",
                    "invalid",
                    1.0,
                ),
            )
    finally:
        connection.close()


def test_migration_enforces_knowledge_item_foreign_keys(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO knowledge_items (
                    knowledge_id, doc_id, chunk_id, summary, entities_json, topics_json, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "knowledge-invalid",
                    "missing-doc",
                    "missing-chunk",
                    "summary",
                    "[]",
                    "[]",
                    0.8,
                ),
            )
    finally:
        connection.close()


def test_migration_enforces_chunk_char_range_constraint(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO documents (
                doc_id, path, relative_path, source_root_id, source_path, hash_sha256,
                title, file_type, size_bytes, created_at, modified_at, parse_status,
                sensitivity, is_deleted_from_fs
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "doc-range-1",
                "/tmp/range.md",
                "range.md",
                "source-1",
                "/tmp/range.md",
                "a" * 64,
                "range",
                "md",
                128,
                "2026-03-03T00:00:00",
                "2026-03-03T00:00:00",
                "success",
                "internal",
                0,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO chunks (
                    chunk_id, doc_id, chunk_index, text, char_start, char_end
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("chunk-range-1", "doc-range-1", 0, "bad range", 10, 3),
            )
    finally:
        connection.close()


def test_migration_enforces_memory_ttl_non_negative(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO memory_items (
                    memory_id, memory_type, scope_type, scope_id, key, content, importance,
                    status, ttl_days, confirmed_count, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "memory-negative-ttl",
                    "M1",
                    "task",
                    "task-1",
                    "deadline",
                    "soon",
                    0.8,
                    "active",
                    -1,
                    0,
                    "2026-03-03T00:00:00",
                ),
            )
    finally:
        connection.close()


def test_migration_enforces_plan_item_count_non_negative(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO file_operation_plans (
                    plan_id, operation_type, status, item_count, risk_level, preview_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "plan-negative-item-count",
                    "move",
                    "draft",
                    -5,
                    "low",
                    "{}",
                ),
            )
    finally:
        connection.close()


def test_chunk_fts_triggers_sync_on_insert_update_delete(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO documents (
                doc_id, path, relative_path, source_root_id, source_path, hash_sha256,
                title, file_type, size_bytes, created_at, modified_at, parse_status,
                sensitivity, is_deleted_from_fs
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "doc-fts-1",
                "/tmp/fts.md",
                "fts.md",
                "source-1",
                "/tmp/fts.md",
                "a" * 64,
                "fts",
                "md",
                128,
                "2026-03-03T00:00:00",
                "2026-03-03T00:00:00",
                "success",
                "internal",
                0,
            ),
        )
        connection.execute(
            """
            INSERT INTO chunks (
                chunk_id, doc_id, chunk_index, text, char_start, char_end
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("chunk-fts-1", "doc-fts-1", 0, "initial phrase", 0, 14),
        )
        connection.commit()

        inserted = connection.execute(
            "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'initial'"
        ).fetchall()
        assert inserted == [("chunk-fts-1",)]

        connection.execute(
            "UPDATE chunks SET text = ?, char_end = ? WHERE chunk_id = ?",
            ("updated phrase", 14, "chunk-fts-1"),
        )
        connection.commit()

        updated = connection.execute(
            "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'updated'"
        ).fetchall()
        old_term = connection.execute(
            "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'initial'"
        ).fetchall()
        assert updated == [("chunk-fts-1",)]
        assert old_term == []

        connection.execute("DELETE FROM chunks WHERE chunk_id = ?", ("chunk-fts-1",))
        connection.commit()
        deleted = connection.execute(
            "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'updated'"
        ).fetchall()
        assert deleted == []
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


def test_migrate_fails_fast_on_duplicate_version_prefixes(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_a = db_path.parent / "0003_a.sql"
    migration_b = db_path.parent / "0003_b.sql"
    migration_a.write_text("CREATE TABLE duplicate_a (id TEXT PRIMARY KEY);", encoding="utf-8")
    migration_b.write_text("CREATE TABLE duplicate_b (id TEXT PRIMARY KEY);", encoding="utf-8")

    from opendocs.storage import db as db_module

    monkeypatch.setattr(db_module, "_list_migration_files", lambda: [migration_a, migration_b])

    with pytest.raises(ValueError, match="duplicate migration version prefix detected: 0003"):
        db_module.migrate(db_path)

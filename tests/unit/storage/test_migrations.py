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
    assert first_applied == ["0001", "0002", "0003", "0004", "0005", "0006"]
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
        assert versions == {"0001", "0002", "0003", "0004", "0005", "0006"}
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
                    "11111111-1111-4111-8111-111111111111",
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


def test_migration_backfills_audit_target_type_guardrail_for_legacy_tables(db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO schema_migrations(version, filename, applied_at)
            VALUES ('0001', '0001_initial.sql', '2026-03-03T00:00:00Z')
            """
        )
        # Simulate a legacy schema where all S1 tables exist but some CHECK constraints are missing.
        connection.execute(
            """
            CREATE TABLE documents (
                doc_id TEXT PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                relative_path TEXT NOT NULL,
                source_root_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                hash_sha256 TEXT NOT NULL,
                title TEXT NOT NULL,
                file_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                modified_at TEXT NOT NULL,
                indexed_at TEXT,
                parse_status TEXT NOT NULL,
                category TEXT,
                tags_json TEXT NOT NULL DEFAULT '[]',
                sensitivity TEXT NOT NULL,
                is_deleted_from_fs INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE chunks (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                char_start INTEGER NOT NULL,
                char_end INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE knowledge_items (
                knowledge_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                entities_json TEXT NOT NULL DEFAULT '[]',
                topics_json TEXT NOT NULL DEFAULT '[]',
                confidence REAL NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE relation_edges (
                edge_id TEXT PRIMARY KEY,
                src_type TEXT NOT NULL,
                src_id TEXT NOT NULL,
                dst_type TEXT NOT NULL,
                dst_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                weight REAL NOT NULL,
                evidence_chunk_id TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE memory_items (
                memory_id TEXT PRIMARY KEY,
                memory_type TEXT,
                scope_type TEXT,
                scope_id TEXT,
                key TEXT,
                content TEXT,
                importance REAL,
                status TEXT,
                ttl_days INTEGER
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE file_operation_plans (
                plan_id TEXT PRIMARY KEY,
                operation_type TEXT,
                status TEXT,
                item_count INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE audit_logs (
                audit_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                actor TEXT NOT NULL CHECK (actor IN ('user', 'system', 'model')),
                operation TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                result TEXT NOT NULL CHECK (result IN ('success', 'failure')),
                detail_json TEXT NOT NULL DEFAULT '{}',
                trace_id TEXT NOT NULL
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    applied = migrate(db_path)
    assert applied == ["0002", "0003", "0004", "0005", "0006"]

    verify_connection = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            verify_connection.execute(
                """
                INSERT INTO audit_logs (
                    audit_id, timestamp, actor, operation, target_type,
                    target_id, result, detail_json, trace_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "22222222-2222-4222-8222-222222222222",
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
        verify_connection.close()


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
                    "33333333-3333-4333-8333-333333333333",
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
                    "44444444-4444-4444-8444-444444444444",
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
                "55555555-5555-4555-8555-555555555555",
                "/tmp/range.md",
                "range.md",
                "66666666-6666-4666-8666-666666666666",
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
                (
                    "77777777-7777-4777-8777-777777777777",
                    "55555555-5555-4555-8555-555555555555",
                    0,
                    "bad range",
                    10,
                    3,
                ),
            )
    finally:
        connection.close()


def test_migration_enforces_document_id_and_hash_format(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO documents (
                    doc_id, path, relative_path, source_root_id, source_path, hash_sha256,
                    title, file_type, size_bytes, created_at, modified_at, parse_status,
                    sensitivity, is_deleted_from_fs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "not-a-uuid",
                    "/tmp/invalid-id.md",
                    "invalid-id.md",
                    "11111111-1111-4111-8111-111111111111",
                    "/tmp/invalid-id.md",
                    "a" * 64,
                    "invalid-id",
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
                INSERT INTO documents (
                    doc_id, path, relative_path, source_root_id, source_path, hash_sha256,
                    title, file_type, size_bytes, created_at, modified_at, parse_status,
                    sensitivity, is_deleted_from_fs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "12121212-1212-4121-8121-121212121212",
                    "/tmp/invalid-hash.md",
                    "invalid-hash.md",
                    "34343434-3434-4343-8343-343434343434",
                    "/tmp/invalid-hash.md",
                    "G" * 64,
                    "invalid-hash",
                    "md",
                    128,
                    "2026-03-03T00:00:00",
                    "2026-03-03T00:00:00",
                    "success",
                    "internal",
                    0,
                ),
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
                    "88888888-8888-4888-8888-888888888888",
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
                    "99999999-9999-4999-8999-999999999999",
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
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "/tmp/fts.md",
                "fts.md",
                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
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
            (
                "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                0,
                "initial phrase",
                0,
                14,
            ),
        )
        connection.commit()

        inserted = connection.execute(
            "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'initial'"
        ).fetchall()
        assert inserted == [("cccccccc-cccc-4ccc-8ccc-cccccccccccc",)]

        connection.execute(
            "UPDATE chunks SET text = ?, char_end = ? WHERE chunk_id = ?",
            ("updated phrase", 14, "cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
        )
        connection.commit()

        updated = connection.execute(
            "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'updated'"
        ).fetchall()
        old_term = connection.execute(
            "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'initial'"
        ).fetchall()
        assert updated == [("cccccccc-cccc-4ccc-8ccc-cccccccccccc",)]
        assert old_term == []

        connection.execute(
            "DELETE FROM chunks WHERE chunk_id = ?",
            ("cccccccc-cccc-4ccc-8ccc-cccccccccccc",),
        )
        connection.commit()
        deleted = connection.execute(
            "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'updated'"
        ).fetchall()
        deleted_by_id = connection.execute(
            "SELECT COUNT(*) FROM chunk_fts WHERE chunk_id = ?",
            ("cccccccc-cccc-4ccc-8ccc-cccccccccccc",),
        ).fetchone()
        assert deleted == []
        assert deleted_by_id == (0,)
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

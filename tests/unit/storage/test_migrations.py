"""Migration tests for S1 storage baseline."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import Engine

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
    assert first_applied == ["0001"]
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
        assert versions == {"0001"}
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


def test_migration_accepts_expanded_target_types(db_path: Path) -> None:
    """S3+ target_type values must be accepted."""
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        for i, target_type in enumerate(("source", "search", "provider_call")):
            hex_i = format(i + 1, "x")
            audit_id = f"{hex_i * 8}-{hex_i * 4}-4{hex_i * 3}-8{hex_i * 3}-{hex_i * 12}"
            connection.execute(
                """
                INSERT INTO audit_logs (
                    audit_id, timestamp, actor, operation, target_type,
                    target_id, result, detail_json, trace_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    "2026-03-05T00:00:00Z",
                    "system",
                    "test_op",
                    target_type,
                    f"target-{i}",
                    "success",
                    "{}",
                    f"trace-{i}",
                ),
            )
        connection.commit()
        count = connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        assert count == 3
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


def test_migration_enforces_confidence_range(db_path: Path) -> None:
    """knowledge_items.confidence must be in [0.0, 1.0]."""
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        # Insert a parent document and chunk first
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
                "/tmp/conf.md",
                "conf.md",
                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                "/tmp/conf.md",
                "a" * 64,
                "conf",
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
                "text",
                0,
                4,
            ),
        )
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO knowledge_items (
                    knowledge_id, doc_id, chunk_id, summary, confidence
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
                    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                    "bad confidence",
                    1.5,
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


def test_migration_failure_leaves_db_usable_for_retry(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a migration fails, the DB must still be usable and re-runnable.

    Specifically: if migration 0001 succeeds but a subsequent migration fails,
    the successfully applied migration must remain recorded, and a retry must
    skip the already-applied one and only re-attempt the failed one.
    """
    from opendocs.storage import db as db_module

    real_files = db_module._list_migration_files()

    bad_sql = db_path.parent / "0002_bad_retry.sql"
    bad_sql.write_text(
        "INSERT INTO not_exists_table (id) VALUES ('boom');",
        encoding="utf-8",
    )

    monkeypatch.setattr(db_module, "_list_migration_files", lambda: real_files + [bad_sql])

    # First run: 0001 succeeds, 0002 fails
    with pytest.raises(sqlite3.Error):
        db_module.migrate(db_path)

    # 0001 should be recorded as applied
    connection = sqlite3.connect(db_path)
    try:
        applied = {
            row[0] for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
        }
        assert "0001" in applied
        assert "0002" not in applied

        # Core tables from 0001 should exist
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "documents" in tables
    finally:
        connection.close()

    # Retry with the bad migration removed — should succeed with no new applies
    monkeypatch.setattr(db_module, "_list_migration_files", lambda: real_files)
    second_applied = db_module.migrate(db_path)
    assert second_applied == []


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


def test_chunk_fts_triggers_sync_via_orm(engine: Engine) -> None:
    """FTS trigger sync must also work when writes go through SQLAlchemy ORM."""
    import uuid

    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from opendocs.domain.models import ChunkModel, DocumentModel
    from opendocs.utils.time import utcnow_naive

    now = utcnow_naive()
    doc_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())

    with Session(engine) as session:
        doc = DocumentModel(
            doc_id=doc_id,
            path="/tmp/fts_orm.md",
            relative_path="fts_orm.md",
            source_root_id=str(uuid.uuid4()),
            source_path="/tmp/fts_orm.md",
            hash_sha256="a" * 64,
            title="fts-orm",
            file_type="md",
            size_bytes=64,
            created_at=now,
            modified_at=now,
            parse_status="success",
        )
        session.add(doc)
        session.flush()

        chunk = ChunkModel(
            chunk_id=chunk_id,
            doc_id=doc_id,
            chunk_index=0,
            text="hello orm fts trigger",
            char_start=0,
            char_end=20,
        )
        session.add(chunk)
        session.commit()

        # INSERT trigger: FTS should contain the text
        rows = session.execute(
            text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'hello'")
        ).fetchall()
        assert rows == [(chunk_id,)]

        # UPDATE trigger: old term removed, new term indexed
        chunk.text = "goodbye orm fts trigger"
        session.commit()

        rows_new = session.execute(
            text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'goodbye'")
        ).fetchall()
        rows_old = session.execute(
            text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'hello'")
        ).fetchall()
        assert rows_new == [(chunk_id,)]
        assert rows_old == []

        # DELETE trigger: entry removed from FTS
        session.delete(chunk)
        session.commit()

        rows_del = session.execute(
            text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'goodbye'")
        ).fetchall()
        assert rows_del == []


# ---------------------------------------------------------------------------
# init_db.py script CLI tests (S1 deliverable: scripts/init_db.py)
# ---------------------------------------------------------------------------


def test_migration_enforces_chunk_index_non_negative(db_path: Path) -> None:
    """chunks.chunk_index must be >= 0."""
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
                "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
                "/tmp/neg_idx.md",
                "neg_idx.md",
                "ffffffff-ffff-4fff-8fff-ffffffffffff",
                "/tmp/neg_idx.md",
                "a" * 64,
                "neg idx",
                "md",
                128,
                "2026-03-03 00:00:00",
                "2026-03-03 00:00:00",
                "success",
                "internal",
                0,
            ),
        )
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO chunks (
                    chunk_id, doc_id, chunk_index, text, char_start, char_end
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
                    "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
                    -1,
                    "negative index",
                    0,
                    14,
                ),
            )
    finally:
        connection.close()


def test_migration_timestamp_format_no_iso_t(db_path: Path) -> None:
    """ADR-0003: schema_migrations.applied_at must use 'YYYY-MM-DD HH:MM:SS' (no T)."""
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute("SELECT applied_at FROM schema_migrations").fetchall()
        assert len(rows) > 0
        for (applied_at,) in rows:
            assert "T" not in applied_at, f"applied_at contains ISO 'T': {applied_at}"
            # Verify it matches the expected pattern
            assert len(applied_at) == 19, f"unexpected length: {applied_at}"
            assert applied_at[10] == " ", f"position 10 should be space: {applied_at}"
    finally:
        connection.close()


def test_init_db_script_creates_database(tmp_path: Path) -> None:
    """scripts/init_db.py --db-path creates a new database with all tables."""
    import importlib.util

    script_path = Path(__file__).resolve().parents[3] / "scripts" / "init_db.py"
    spec = importlib.util.spec_from_file_location("init_db_script", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    target = tmp_path / "test_init.db"
    exit_code = mod.main(["--db-path", str(target)])
    assert exit_code == 0
    assert target.exists()

    connection = sqlite3.connect(target)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
        }
        assert "documents" in tables
        assert "chunks" in tables
        assert "audit_logs" in tables
    finally:
        connection.close()


def test_init_db_script_is_idempotent(tmp_path: Path) -> None:
    """Running init_db.py twice on the same database succeeds without error."""
    import importlib.util

    script_path = Path(__file__).resolve().parents[3] / "scripts" / "init_db.py"
    spec = importlib.util.spec_from_file_location("init_db_script", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    target = tmp_path / "test_idempotent.db"
    assert mod.main(["--db-path", str(target)]) == 0
    assert mod.main(["--db-path", str(target)]) == 0

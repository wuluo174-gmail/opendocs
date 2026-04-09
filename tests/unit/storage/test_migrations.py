"""Migration tests for S1 storage baseline."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import Engine

from opendocs.domain.models import SourceRootModel
from opendocs.exceptions import SchemaCompatibilityError
from opendocs.storage.db import build_sqlite_engine, init_db, migrate, validate_schema_compatibility
from opendocs.utils.path_facts import (
    build_display_path,
    derive_directory_facts,
    derive_source_display_root,
)
from opendocs.utils.time import utcnow_naive


def _list_tables(db_path: Path) -> set[str]:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        connection.close()


def _insert_source_root(
    connection: sqlite3.Connection,
    *,
    source_root_id: str,
    path: str,
) -> None:
    connection.execute(
        """
        INSERT INTO source_roots (
            source_root_id, path, display_root, label, exclude_rules_json,
            recursive, is_active, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_root_id,
            path,
            derive_source_display_root(path, source_root_id=source_root_id),
            "test source",
            "{}",
            1,
            1,
            "2026-03-03T00:00:00",
            "2026-03-03T00:00:00",
        ),
    )


def _insert_document(
    connection: sqlite3.Connection,
    *,
    doc_id: str,
    path: str,
    relative_path: str,
    source_root_id: str,
    source_path: str | None = None,
    hash_sha256: str | None = "a" * 64,
    title: str = "test document",
    file_type: str = "md",
    size_bytes: int = 128,
    created_at: str = "2026-03-03T00:00:00",
    modified_at: str = "2026-03-03T00:00:00",
    parse_status: str = "success",
    sensitivity: str = "internal",
    is_deleted_from_fs: int = 0,
) -> None:
    directory_path, relative_directory_path = derive_directory_facts(path, relative_path)
    display_root_row = connection.execute(
        "SELECT display_root FROM source_roots WHERE source_root_id = ?",
        (source_root_id,),
    ).fetchone()
    if display_root_row is None:
        raise AssertionError(f"missing source_root for test helper: {source_root_id}")
    connection.execute(
        """
        INSERT INTO documents (
            doc_id, path, relative_path, display_path, directory_path,
            relative_directory_path, source_root_id, source_path, hash_sha256,
            title, file_type, size_bytes, created_at, modified_at, parse_status,
            sensitivity, is_deleted_from_fs
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            doc_id,
            path,
            relative_path,
            build_display_path(display_root_row[0], relative_path),
            directory_path,
            relative_directory_path,
            source_root_id,
            source_path or path,
            hash_sha256,
            title,
            file_type,
            size_bytes,
            created_at,
            modified_at,
            parse_status,
            sensitivity,
            is_deleted_from_fs,
        ),
    )


def _write_stale_development_db(db_path: Path) -> None:
    """Create a legacy dev DB that claims current versions but lacks new invariants."""
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE schema_migrations (
                version TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );

            CREATE TABLE source_roots (
                source_root_id TEXT PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                label TEXT,
                exclude_rules_json TEXT NOT NULL DEFAULT '{}',
                recursive INTEGER NOT NULL DEFAULT 1,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

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
                parse_status TEXT NOT NULL DEFAULT 'success',
                category TEXT,
                tags_json TEXT NOT NULL DEFAULT '[]',
                sensitivity TEXT NOT NULL DEFAULT 'internal',
                is_deleted_from_fs INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE scan_runs (
                scan_run_id TEXT PRIMARY KEY,
                source_root_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                included_count INTEGER NOT NULL DEFAULT 0,
                excluded_count INTEGER NOT NULL DEFAULT 0,
                unsupported_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                error_summary_json TEXT NOT NULL DEFAULT '[]',
                trace_id TEXT NOT NULL
            );
            """
        )
        for version in ("0001", "0002", "0003", "0004", "0006"):
            connection.execute(
                """
                INSERT INTO schema_migrations (version, filename, applied_at)
                VALUES (?, ?, ?)
                """,
                (version, f"{version}_legacy.sql", "2026-03-20 00:00:00"),
            )
        connection.commit()
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
    assert "task_events" in tables
    assert "memory_items" in tables
    assert "file_operation_plans" in tables
    assert "audit_logs" in tables
    assert "chunk_fts" in tables
    assert "index_artifacts" in tables
    assert "index_artifact_generations" in tables


def test_migrate_is_idempotent(db_path: Path) -> None:
    first_applied = migrate(db_path)
    second_applied = migrate(db_path)
    assert first_applied == [
        "0001",
        "0002",
        "0003",
        "0004",
        "0006",
        "0007",
        "0008",
        "0009",
        "0010",
        "0011",
        "0012",
        "0013",
        "0014",
        "0015",
        "0016",
        "0017",
    ]
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
        assert versions == {
            "0001",
            "0002",
            "0003",
            "0004",
            "0006",
            "0007",
            "0008",
            "0009",
            "0010",
            "0011",
            "0012",
            "0013",
            "0014",
            "0015",
            "0016",
            "0017",
        }
    finally:
        connection.close()


def test_migration_adds_document_file_identity_column_and_index(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)").fetchall()}
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(documents)").fetchall()}
        file_identity_index_sql = connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'index' AND name = 'idx_documents_file_identity'"
        ).fetchone()
        assert "file_identity" in columns
        assert "idx_documents_file_identity" in indexes
        assert file_identity_index_sql is not None
        assert (
            "WHERE file_identity IS NOT NULL AND is_deleted_from_fs = 0"
            in file_identity_index_sql[0]
        )
    finally:
        connection.close()


def test_migration_creates_index_artifact_generations_table_and_indexes(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(index_artifact_generations)").fetchall()
        }
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(index_artifact_generations)").fetchall()
        }
        assert {
            "artifact_name",
            "generation",
            "bundle_path",
            "state",
            "committed_at",
            "retired_at",
            "delete_after",
            "deleted_at",
            "updated_at",
        }.issubset(columns)
        assert "idx_index_artifact_generations_committed" in indexes
        assert "idx_index_artifact_generations_gc_due" in indexes
    finally:
        connection.close()


def test_migration_normalizes_legacy_building_status_into_freshness_only_contract(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opendocs.storage import db as db_module

    all_files = db_module._list_migration_files()
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE schema_migrations (
                version TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );

            CREATE TABLE index_artifacts (
                artifact_name TEXT PRIMARY KEY CHECK (
                    artifact_name IN ('dense_hnsw')
                ),
                status TEXT NOT NULL DEFAULT 'stale' CHECK (
                    status IN ('stale', 'ready', 'building', 'failed')
                ),
                artifact_path TEXT NOT NULL,
                embedder_model TEXT NOT NULL,
                embedder_dim INTEGER NOT NULL CHECK (embedder_dim > 0),
                embedder_signature TEXT NOT NULL,
                generation INTEGER NOT NULL DEFAULT 0 CHECK (generation >= 0),
                active_build_token TEXT,
                build_started_at TEXT,
                lease_expires_at TEXT,
                last_error TEXT,
                last_reason TEXT,
                last_built_at TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE index_artifact_generations (
                artifact_name TEXT NOT NULL,
                generation INTEGER NOT NULL CHECK (generation > 0),
                bundle_path TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('committed', 'retained', 'deleted')),
                committed_at TEXT NOT NULL,
                retired_at TEXT,
                delete_after TEXT,
                deleted_at TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (artifact_name, generation),
                FOREIGN KEY (artifact_name) REFERENCES index_artifacts(artifact_name) ON DELETE CASCADE
            );

            CREATE UNIQUE INDEX idx_index_artifacts_active_build_token
            ON index_artifacts (active_build_token)
            WHERE active_build_token IS NOT NULL;

            CREATE UNIQUE INDEX idx_index_artifact_generations_committed
            ON index_artifact_generations (artifact_name)
            WHERE state = 'committed';

            CREATE INDEX idx_index_artifact_generations_gc_due
            ON index_artifact_generations (state, delete_after)
            WHERE state = 'retained' AND delete_after IS NOT NULL;
            """
        )
        for migration_file in all_files:
            version = migration_file.name.split("_", 1)[0]
            if version in {"0016", "0017"}:
                continue
            connection.execute(
                "INSERT INTO schema_migrations (version, filename, applied_at) VALUES (?, ?, ?)",
                (version, migration_file.name, "2026-03-03 00:00:00"),
            )
        connection.execute(
            """
            INSERT INTO index_artifacts (
                artifact_name, status, artifact_path, embedder_model, embedder_dim,
                embedder_signature, generation, last_reason, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "dense_hnsw",
                "building",
                "/tmp/runtime/index/hnsw/.dense_hnsw_bundles/legacy/chunks.hnsw",
                "local-lsa-v1",
                128,
                "legacy-signature",
                1,
                None,
                "2026-03-03 00:00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setattr(db_module, "_list_migration_files", lambda: all_files)
    applied = db_module.migrate(db_path)
    assert applied == ["0016", "0017"]

    connection = sqlite3.connect(db_path)
    try:
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'index_artifacts'"
        ).fetchone()
        row = connection.execute(
            "SELECT status, last_reason, namespace_path "
            "FROM index_artifacts WHERE artifact_name = 'dense_hnsw'"
        ).fetchone()
        assert table_sql is not None
        assert "status IN ('stale', 'ready', 'failed')" in table_sql[0]
        assert "building" not in table_sql[0]
        assert "namespace_path TEXT NOT NULL" in table_sql[0]
        assert "artifact_path" not in table_sql[0]
        assert row == ("stale", "legacy_building_status", "/tmp/runtime/index/hnsw/chunks.hnsw")
    finally:
        connection.close()


def test_migration_adds_source_root_metadata_default_columns(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        columns = {
            row[1]: {"notnull": bool(row[3]), "default": row[4]}
            for row in connection.execute("PRAGMA table_info(source_roots)").fetchall()
        }
        assert "default_category" in columns
        assert "default_tags_json" in columns
        assert "default_sensitivity" in columns
        assert "source_config_rev" in columns
        assert "display_root" in columns
        assert columns["default_tags_json"]["notnull"] is True
        assert columns["default_tags_json"]["default"] == "'[]'"
        assert columns["source_config_rev"]["notnull"] is True
        assert columns["source_config_rev"]["default"] == "1"
    finally:
        connection.close()


def test_migration_adds_document_source_config_rev_column(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        columns = {
            row[1]: {"notnull": bool(row[3]), "default": row[4]}
            for row in connection.execute("PRAGMA table_info(documents)").fetchall()
        }
        assert "display_path" in columns
        assert "source_config_rev" in columns
        assert columns["source_config_rev"]["notnull"] is True
        assert columns["source_config_rev"]["default"] == "1"
    finally:
        connection.close()


def test_migration_scopes_document_path_uniqueness_to_active_rows(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_source_root(
            connection,
            source_root_id="a9a9a9a9-a9a9-4a9a-8a9a-111111111111",
            path="/tmp/path-scope-root",
        )
        active_index_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
            ("idx_documents_active_path",),
        ).fetchone()
        assert active_index_sql is not None
        assert "WHERE is_deleted_from_fs = 0" in active_index_sql[0]

        common_values = (
            "same/path.md",
            "path-scope-root/same/path.md",
            "/tmp/path-scope-root/same",
            "same",
            "a9a9a9a9-a9a9-4a9a-8a9a-111111111111",
            "/tmp/path-scope-root/same/path.md",
            "a" * 64,
            "scoped path",
            "md",
            100,
            "2026-03-03 00:00:00",
            "2026-03-03 00:00:00",
            "success",
            "internal",
        )
        connection.execute(
            """
            INSERT INTO documents (
                doc_id, path, relative_path, display_path, directory_path,
                relative_directory_path, source_root_id, source_path, hash_sha256,
                title, file_type, size_bytes, created_at, modified_at, parse_status,
                sensitivity, is_deleted_from_fs
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "11111111-1111-4111-8111-111111111111",
                "/tmp/path-scope-root/same/path.md",
                *common_values,
                1,
            ),
        )
        connection.execute(
            """
            INSERT INTO documents (
                doc_id, path, relative_path, display_path, directory_path,
                relative_directory_path, source_root_id, source_path, hash_sha256,
                title, file_type, size_bytes, created_at, modified_at, parse_status,
                sensitivity, is_deleted_from_fs
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "22222222-2222-4222-8222-222222222222",
                "/tmp/path-scope-root/same/path.md",
                *common_values,
                0,
            ),
        )
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO documents (
                    doc_id, path, relative_path, display_path, directory_path,
                    relative_directory_path, source_root_id, source_path, hash_sha256,
                    title, file_type, size_bytes, created_at, modified_at, parse_status,
                    sensitivity, is_deleted_from_fs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "33333333-3333-4333-8333-333333333333",
                    "/tmp/path-scope-root/same/path.md",
                    *common_values,
                    0,
                ),
            )
        connection.rollback()
    finally:
        connection.close()


def test_index_artifacts_constraints(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO index_artifacts (
                    artifact_name, status, namespace_path, embedder_model,
                    embedder_dim, embedder_signature
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "dense_hnsw",
                    "ready",
                    "/tmp/chunks.hnsw",
                    "local-ngram-hash-v1",
                    0,
                    "bad|dim=0",
                ),
            )
    finally:
        connection.close()


def test_index_artifacts_build_lease_columns_and_index(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        columns = {
            row[1]: {"notnull": bool(row[3]), "default": row[4]}
            for row in connection.execute("PRAGMA table_info(index_artifacts)").fetchall()
        }
        assert "namespace_path" in columns
        assert "generation" in columns
        assert columns["generation"]["notnull"] is True
        assert "active_build_token" in columns
        assert "build_started_at" in columns
        assert "lease_expires_at" in columns

        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(index_artifacts)").fetchall()
        }
        assert "idx_index_artifacts_active_build_token" in indexes
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
        source_root_id = "66666666-6666-4666-8666-666666666666"
        _insert_source_root(connection, source_root_id=source_root_id, path="/tmp")
        _insert_document(
            connection,
            doc_id="55555555-5555-4555-8555-555555555555",
            path="/tmp/range.md",
            relative_path="range.md",
            source_root_id=source_root_id,
            title="range",
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


def test_migration_enforces_chunk_locator_constraints(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        source_root_id = "20202020-2020-4020-8020-202020202020"
        _insert_source_root(connection, source_root_id=source_root_id, path="/tmp")
        _insert_document(
            connection,
            doc_id="10101010-1010-4010-8010-101010101010",
            path="/tmp/locator.md",
            relative_path="locator.md",
            source_root_id=source_root_id,
            title="locator",
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO chunks (
                    chunk_id, doc_id, chunk_index, text, char_start, char_end,
                    page_no, paragraph_start, paragraph_end
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "30303030-3030-4030-8030-303030303030",
                    "10101010-1010-4010-8010-101010101010",
                    0,
                    "bad locator",
                    -1,
                    10,
                    -1,
                    -3,
                    -2,
                ),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO chunks (
                    chunk_id, doc_id, chunk_index, text, char_start, char_end,
                    paragraph_start, paragraph_end
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "40404040-4040-4040-8040-404040404040",
                    "10101010-1010-4010-8010-101010101010",
                    1,
                    "bad paragraph range",
                    0,
                    19,
                    5,
                    3,
                ),
            )
    finally:
        connection.close()


def test_migration_enforces_document_id_and_hash_format(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        _insert_source_root(
            connection,
            source_root_id="11111111-1111-4111-8111-111111111111",
            path="/tmp/source-invalid-id",
        )
        _insert_source_root(
            connection,
            source_root_id="34343434-3434-4343-8343-343434343434",
            path="/tmp/source-invalid-hash",
        )
        with pytest.raises(sqlite3.IntegrityError):
            _insert_document(
                connection,
                doc_id="not-a-uuid",
                path="/tmp/invalid-id.md",
                relative_path="invalid-id.md",
                source_root_id="11111111-1111-4111-8111-111111111111",
                title="invalid-id",
            )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_document(
                connection,
                doc_id="12121212-1212-4121-8121-121212121212",
                path="/tmp/invalid-hash.md",
                relative_path="invalid-hash.md",
                source_root_id="34343434-3434-4343-8343-343434343434",
                hash_sha256="G" * 64,
                title="invalid-hash",
            )
    finally:
        connection.close()


def test_migration_enforces_memory_review_window_days_non_negative(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO memory_items (
                    memory_id, memory_type, memory_kind, scope_type, scope_id, key, content,
                    source_event_ids_json, evidence_refs_json, importance, confidence, status,
                    review_window_days, user_confirmed_count, recall_count, decay_score,
                    promotion_state, consolidated_from_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "88888888-8888-4888-8888-888888888888",
                    "M1",
                    "task_snapshot",
                    "task",
                    "task-1",
                    "deadline",
                    "soon",
                    "[]",
                    "[]",
                    0.8,
                    0.6,
                    "active",
                    -1,
                    0,
                    0,
                    0.0,
                    "promoted",
                    "[]",
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


def test_migration_drops_legacy_memory_rows_without_task_events(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opendocs.storage import db as db_module

    all_files = db_module._list_migration_files()
    legacy_files = [path for path in all_files if path.name < "0013_task_events_and_memory_contract.sql"]
    monkeypatch.setattr(db_module, "_list_migration_files", lambda: legacy_files)
    db_module.migrate(db_path)

    connection = sqlite3.connect(db_path)
    try:
        connection.execute("DROP INDEX IF EXISTS idx_memory_items_active_scope_key")
        connection.execute("DROP INDEX IF EXISTS idx_memory_items_scope")
        connection.execute("DROP INDEX IF EXISTS idx_memory_items_supersedes_memory")
        connection.execute("DROP TABLE memory_items")
        connection.execute(
            """
            CREATE TABLE memory_items (
                memory_id TEXT PRIMARY KEY,
                memory_type TEXT NOT NULL,
                scope_type TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                key TEXT NOT NULL,
                content TEXT NOT NULL,
                importance REAL NOT NULL DEFAULT 0.5,
                status TEXT NOT NULL DEFAULT 'active',
                ttl_days INTEGER,
                confirmed_count INTEGER NOT NULL DEFAULT 0,
                last_confirmed_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(memory_type, scope_type, scope_id, key)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO memory_items (
                memory_id, memory_type, scope_type, scope_id, key, content, importance,
                status, ttl_days, confirmed_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "99999999-aaaa-4999-8999-999999999999",
                "M1",
                "task",
                "legacy-scope",
                "legacy-key",
                "legacy-content",
                0.7,
                "active",
                30,
                1,
                "2026-03-03T00:00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setattr(db_module, "_list_migration_files", lambda: all_files)
    applied = db_module.migrate(db_path)
    assert applied == ["0013", "0014", "0015", "0016", "0017"]

    connection = sqlite3.connect(db_path)
    try:
        count = connection.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0]
        assert count == 0
    finally:
        connection.close()


def test_migration_enforces_confidence_range(db_path: Path) -> None:
    """knowledge_items.confidence must be in [0.0, 1.0]."""
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        # Insert a parent document and chunk first
        source_root_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        _insert_source_root(connection, source_root_id=source_root_id, path="/tmp")
        _insert_document(
            connection,
            doc_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            path="/tmp/conf.md",
            relative_path="conf.md",
            source_root_id=source_root_id,
            title="conf",
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
        source_root_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        _insert_source_root(connection, source_root_id=source_root_id, path="/tmp")
        _insert_document(
            connection,
            doc_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            path="/tmp/fts.md",
            relative_path="fts.md",
            source_root_id=source_root_id,
            title="fts",
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

    bad_sql = db_path.parent / "0099_bad_retry.sql"
    bad_sql.write_text(
        "INSERT INTO not_exists_table (id) VALUES ('boom');",
        encoding="utf-8",
    )

    monkeypatch.setattr(db_module, "_list_migration_files", lambda: real_files + [bad_sql])

    # First run: 0001+0002 succeed, 0099 fails
    with pytest.raises(sqlite3.Error):
        db_module.migrate(db_path)

    # 0001 and 0002 should be recorded as applied
    connection = sqlite3.connect(db_path)
    try:
        applied = {
            row[0] for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
        }
        assert "0001" in applied
        assert "0002" in applied
        assert "0099" not in applied

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


def test_migration_declares_source_root_foreign_keys(db_path: Path) -> None:
    migrate(db_path)
    connection = sqlite3.connect(db_path)
    try:
        document_fks = {
            (row[3], row[2], row[4], row[6])
            for row in connection.execute("PRAGMA foreign_key_list(documents)").fetchall()
        }
        scan_run_fks = {
            (row[3], row[2], row[4], row[6])
            for row in connection.execute("PRAGMA foreign_key_list(scan_runs)").fetchall()
        }
        assert ("source_root_id", "source_roots", "source_root_id", "RESTRICT") in document_fks
        assert ("source_root_id", "source_roots", "source_root_id", "RESTRICT") in scan_run_fks
    finally:
        connection.close()


def test_init_db_rejects_stale_development_schema(db_path: Path) -> None:
    _write_stale_development_db(db_path)

    with pytest.raises(SchemaCompatibilityError, match="Rebuild the local database"):
        init_db(db_path)


def test_build_sqlite_engine_rejects_stale_development_schema(db_path: Path) -> None:
    _write_stale_development_db(db_path)

    with pytest.raises(SchemaCompatibilityError, match="documents.source_root_id"):
        build_sqlite_engine(db_path)


def test_validate_schema_compatibility_rejects_memory_rows_without_task_event_refs(
    db_path: Path,
) -> None:
    init_db(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO memory_items (
                memory_id, memory_type, memory_kind, scope_type, scope_id, key, content,
                source_event_ids_json, evidence_refs_json, importance, confidence, status,
                review_window_days, user_confirmed_count, recall_count, decay_score,
                promotion_state, consolidated_from_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "12121212-3434-4121-8121-565656565656",
                "M1",
                "task_snapshot",
                "task",
                "task-1",
                "status",
                "ready",
                "[]",
                "[]",
                0.5,
                0.8,
                "active",
                30,
                0,
                0,
                0.0,
                "promoted",
                "[]",
                "2026-03-03 00:00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        SchemaCompatibilityError,
        match="memory_items contains rows without source_event_ids_json backing events",
    ):
        validate_schema_compatibility(db_path)


def test_migration_backfills_directory_facts_for_legacy_documents(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opendocs.storage import db as db_module

    all_files = db_module._list_migration_files()
    legacy_files = [path for path in all_files if path.name < "0006_documents_directory_facts.sql"]
    monkeypatch.setattr(db_module, "_list_migration_files", lambda: legacy_files)
    db_module.migrate(db_path)

    source_root_id = "abababab-abab-4aba-8aba-111111111111"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_source_root(connection, source_root_id=source_root_id, path="/tmp/legacy-root")
        connection.execute(
            """
            INSERT INTO documents (
                doc_id, path, relative_path, display_path, source_root_id, source_path,
                hash_sha256, title, file_type, size_bytes, created_at, modified_at,
                parse_status, sensitivity, is_deleted_from_fs
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "cdcdcdcd-cdcd-4cdc-8cdc-111111111111",
                "/tmp/legacy-root/projects/alpha/report.md",
                "projects/alpha/report.md",
                "legacy-root/projects/alpha/report.md",
                source_root_id,
                "/tmp/legacy-root/projects/alpha/report.md",
                "a" * 64,
                "legacy nested report",
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
    finally:
        connection.close()

    monkeypatch.setattr(db_module, "_list_migration_files", lambda: all_files)
    applied = db_module.migrate(db_path)
    assert applied == [
        "0006",
        "0007",
        "0008",
        "0009",
        "0010",
        "0011",
        "0012",
        "0013",
        "0014",
        "0015",
        "0016",
        "0017",
    ]

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT directory_path, relative_directory_path, source_path
            FROM documents
            WHERE doc_id = ?
            """,
            ("cdcdcdcd-cdcd-4cdc-8cdc-111111111111",),
        ).fetchone()
        assert row == (
            "/tmp/legacy-root/projects/alpha",
            "projects/alpha",
            "/tmp/legacy-root/projects/alpha/report.md",
        )
    finally:
        connection.close()


def test_migration_repairs_legacy_source_path_to_document_path(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opendocs.storage import db as db_module

    all_files = db_module._list_migration_files()
    legacy_files = [path for path in all_files if path.name < "0007_source_path_provenance.sql"]
    monkeypatch.setattr(db_module, "_list_migration_files", lambda: legacy_files)
    db_module.migrate(db_path)

    source_root_id = "efefefef-efef-4efe-8efe-111111111111"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_source_root(connection, source_root_id=source_root_id, path="/tmp/legacy-root")
        connection.execute(
            """
            INSERT INTO documents (
                doc_id, path, relative_path, display_path, source_root_id, source_path,
                hash_sha256, title, file_type, size_bytes, created_at, modified_at,
                parse_status, sensitivity, is_deleted_from_fs
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "dededede-dede-4ded-8ded-111111111111",
                "/tmp/legacy-root/report.md",
                "report.md",
                "legacy-root/report.md",
                source_root_id,
                "/tmp/legacy-root",
                "b" * 64,
                "legacy source path",
                "md",
                64,
                "2026-03-03 00:00:00",
                "2026-03-03 00:00:00",
                "success",
                "internal",
                0,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setattr(db_module, "_list_migration_files", lambda: all_files)
    applied = db_module.migrate(db_path)
    assert applied == [
        "0007",
        "0008",
        "0009",
        "0010",
        "0011",
        "0012",
        "0013",
        "0014",
        "0015",
        "0016",
        "0017",
    ]

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT source_path
            FROM documents
            WHERE doc_id = ?
            """,
            ("dededede-dede-4ded-8ded-111111111111",),
        ).fetchone()
        assert row == ("/tmp/legacy-root/report.md",)
    finally:
        connection.close()


def test_chunk_fts_triggers_sync_via_orm(engine: Engine) -> None:
    """FTS trigger sync must also work when writes go through SQLAlchemy ORM."""
    import uuid

    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from opendocs.domain.models import ChunkModel, DocumentModel

    now = utcnow_naive()
    doc_id = str(uuid.uuid4())
    source_root_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())

    with Session(engine) as session:
        session.add(
            SourceRootModel(
                source_root_id=source_root_id,
                path="/tmp",
                display_root="tmp",
                label="fts orm",
                exclude_rules_json={},
                recursive=True,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        doc = DocumentModel(
            doc_id=doc_id,
            path="/tmp/fts_orm.md",
            relative_path="fts_orm.md",
            display_path="tmp/fts_orm.md",
            directory_path=derive_directory_facts("/tmp/fts_orm.md", "fts_orm.md")[0],
            relative_directory_path=derive_directory_facts("/tmp/fts_orm.md", "fts_orm.md")[1],
            source_root_id=source_root_id,
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
        source_root_id = "ffffffff-ffff-4fff-8fff-ffffffffffff"
        _insert_source_root(connection, source_root_id=source_root_id, path="/tmp")
        _insert_document(
            connection,
            doc_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
            path="/tmp/neg_idx.md",
            relative_path="neg_idx.md",
            source_root_id=source_root_id,
            title="neg idx",
            created_at="2026-03-03 00:00:00",
            modified_at="2026-03-03 00:00:00",
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


def test_init_db_script_reports_schema_incompatibility(tmp_path: Path, capsys) -> None:
    """init_db.py must fail fast on stale dev DBs instead of silently continuing."""
    import importlib.util

    script_path = Path(__file__).resolve().parents[3] / "scripts" / "init_db.py"
    spec = importlib.util.spec_from_file_location("init_db_script", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    target = tmp_path / "stale.db"
    _write_stale_development_db(target)

    exit_code = mod.main(["--db-path", str(target)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "schema error:" in captured.out
    assert "Rebuild the local database" in captured.out

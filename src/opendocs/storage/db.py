"""Database initialization and migration helpers for SQLite."""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from opendocs.exceptions import SchemaCompatibilityError
from opendocs.utils.time import utcnow_naive

# Shared PRAGMA settings applied to both raw sqlite3 and SQLAlchemy connections.
_SQLITE_PRAGMAS: tuple[str, ...] = (
    "PRAGMA foreign_keys = ON",
    "PRAGMA journal_mode = WAL",
    "PRAGMA busy_timeout = 5000",
)

_MIGRATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


def _resolve_db_path(db_path: str | Path) -> Path:
    resolved = Path(db_path).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _schema_dir() -> Path:
    return Path(__file__).resolve().parent / "schema"


def _list_migration_files() -> list[Path]:
    return sorted(_schema_dir().glob("[0-9][0-9][0-9][0-9]_*.sql"))


def _extract_version(filename: str) -> str:
    return filename.split("_", 1)[0]


def _assert_unique_migration_versions(migration_files: list[Path]) -> None:
    seen_versions: set[str] = set()
    duplicate_versions: set[str] = set()
    for migration_file in migration_files:
        version = _extract_version(migration_file.name)
        if version in seen_versions:
            duplicate_versions.add(version)
        else:
            seen_versions.add(version)
    if duplicate_versions:
        duplicate_text = ", ".join(sorted(duplicate_versions))
        raise ValueError(f"duplicate migration version prefix detected: {duplicate_text}")


def _connect_sqlite(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    for pragma in _SQLITE_PRAGMAS:
        connection.execute(pragma)
    return connection


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _table_sql(connection: sqlite3.Connection, table_name: str) -> str | None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if row is None:
        return None
    return row[0]


def _index_sql(connection: sqlite3.Connection, index_name: str) -> str | None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
        (index_name,),
    ).fetchone()
    if row is None:
        return None
    return row[0]


def _normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def _table_info_map(connection: sqlite3.Connection, table_name: str) -> dict[str, sqlite3.Row]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1]: row for row in rows}


def _has_foreign_key(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    from_column: str,
    target_table: str,
    target_column: str,
    on_delete: str,
) -> bool:
    rows = connection.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
    expected_on_delete = on_delete.upper()
    return any(
        row[3] == from_column
        and row[2] == target_table
        and row[4] == target_column
        and str(row[6]).upper() == expected_on_delete
        for row in rows
    )


def _schema_compatibility_issues(connection: sqlite3.Connection) -> list[str]:
    issues: list[str] = []

    if _table_sql(connection, "schema_migrations") is None:
        issues.append("schema_migrations table is missing")
        return issues

    source_roots_sql = _table_sql(connection, "source_roots")
    if source_roots_sql is None:
        issues.append("source_roots table is missing")
    else:
        source_root_columns = _table_info_map(connection, "source_roots")
        if "default_category" not in source_root_columns:
            issues.append("source_roots.default_category column is missing")
        if "default_tags_json" not in source_root_columns:
            issues.append("source_roots.default_tags_json column is missing")
        if "default_sensitivity" not in source_root_columns:
            issues.append("source_roots.default_sensitivity column is missing")
        if "source_config_rev" not in source_root_columns:
            issues.append("source_roots.source_config_rev column is missing")

    documents_sql = _table_sql(connection, "documents")
    if documents_sql is None:
        issues.append("documents table is missing")
    else:
        document_columns = _table_info_map(connection, "documents")
        hash_column = document_columns.get("hash_sha256")
        if hash_column is None:
            issues.append("documents.hash_sha256 column is missing")
        elif bool(hash_column[3]):
            issues.append("documents.hash_sha256 is still NOT NULL")

        if not _has_foreign_key(
            connection,
            table_name="documents",
            from_column="source_root_id",
            target_table="source_roots",
            target_column="source_root_id",
            on_delete="RESTRICT",
        ):
            issues.append("documents.source_root_id foreign key is missing")

        normalized_documents_sql = _normalize_sql(documents_sql)
        if "file_identity" not in document_columns:
            issues.append("documents.file_identity column is missing")
        if "source_config_rev" not in document_columns:
            issues.append("documents.source_config_rev column is missing")
        if "path text not null unique" in normalized_documents_sql:
            issues.append(
                "documents.path still uses global UNIQUE instead of active-path uniqueness"
            )
        if "check (parse_status = 'failed' or hash_sha256 is not null)" not in (
            normalized_documents_sql
        ):
            issues.append("documents is missing the failed-document hash rule")
        active_path_index_sql = _index_sql(connection, "idx_documents_active_path")
        if active_path_index_sql is None:
            issues.append("documents idx_documents_active_path index is missing")
        elif "where is_deleted_from_fs = 0" not in _normalize_sql(active_path_index_sql):
            issues.append("documents idx_documents_active_path is not scoped to active rows")

    scan_runs_sql = _table_sql(connection, "scan_runs")
    if scan_runs_sql is None:
        issues.append("scan_runs table is missing")
    elif not _has_foreign_key(
        connection,
        table_name="scan_runs",
        from_column="source_root_id",
        target_table="source_roots",
        target_column="source_root_id",
        on_delete="RESTRICT",
    ):
        issues.append("scan_runs.source_root_id foreign key is missing")

    return issues


def _applied_migration_versions(connection: sqlite3.Connection) -> set[str]:
    if _table_sql(connection, "schema_migrations") is None:
        return set()
    rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def _raise_preflight_schema_incompatibility(issues: list[str], db_path: Path) -> None:
    joined_issues = "; ".join(issues)
    raise SchemaCompatibilityError(
        "database schema is incompatible with the current OpenDocs development baseline: "
        f"{joined_issues}. This project is still in development and has no historical "
        f"user data to preserve. Rebuild the local database at {db_path} and rerun "
        "initialization."
    )


def _preflight_pending_migrations(
    connection: sqlite3.Connection,
    *,
    db_path: Path,
    pending_versions: set[str],
) -> None:
    applied_versions = _applied_migration_versions(connection)
    issues: list[str] = []

    if "0007" in pending_versions and "0006" in applied_versions:
        document_columns = _table_info_map(connection, "documents")
        if "directory_path" not in document_columns:
            issues.append("documents.directory_path is missing even though migration 0006 is applied")
        if "relative_directory_path" not in document_columns:
            issues.append(
                "documents.relative_directory_path is missing even though migration 0006 is applied"
            )

    if issues:
        _raise_preflight_schema_incompatibility(issues, db_path)


def validate_schema_compatibility(db_path: str | Path) -> None:
    """Fail fast when a local dev DB no longer matches the current schema baseline."""
    resolved = _resolve_db_path(db_path)
    connection = _connect_sqlite(resolved)
    try:
        issues = _schema_compatibility_issues(connection)
    finally:
        connection.close()

    if issues:
        joined_issues = "; ".join(issues)
        raise SchemaCompatibilityError(
            "database schema is incompatible with the current OpenDocs development baseline: "
            f"{joined_issues}. This project is still in development and has no historical "
            f"user data to preserve. Rebuild the local database at {resolved} and rerun "
            "initialization."
        )


def _apply_migration_atomically(
    connection: sqlite3.Connection,
    *,
    version: str,
    filename: str,
    migration_sql: str,
) -> None:
    # ADR-0003: use "YYYY-MM-DD HH:MM:SS" (no ISO 8601 'T') for SQLite consistency.
    applied_at = utcnow_naive().strftime("%Y-%m-%d %H:%M:%S")
    script = (
        "BEGIN IMMEDIATE;\n"
        f"{migration_sql}\n"
        "INSERT INTO schema_migrations (version, filename, applied_at) VALUES "
        f"({_sql_literal(version)}, {_sql_literal(filename)}, {_sql_literal(applied_at)});\n"
        "COMMIT;\n"
    )
    try:
        # executescript() issues an implicit COMMIT before executing the script,
        # closing any open transaction. This is safe here because we explicitly
        # BEGIN IMMEDIATE in the script itself, so the migration runs atomically.
        # The implicit COMMIT only affects any prior auto-started transaction
        # from the schema_migrations SELECT, which is read-only and idempotent.
        connection.executescript(script)
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise


def migrate(db_path: str | Path) -> list[str]:
    """Apply pending schema SQL files in order and return applied versions."""
    resolved = _resolve_db_path(db_path)
    applied_versions: list[str] = []
    migration_files = _list_migration_files()
    _assert_unique_migration_versions(migration_files)
    connection = _connect_sqlite(resolved)
    try:
        connection.execute(_MIGRATION_TABLE_SQL)
        connection.commit()
        applied_versions_in_db = _applied_migration_versions(connection)
        pending_versions = {
            _extract_version(migration_file.name)
            for migration_file in migration_files
            if _extract_version(migration_file.name) not in applied_versions_in_db
        }
        _preflight_pending_migrations(
            connection,
            db_path=resolved,
            pending_versions=pending_versions,
        )
        for migration_file in migration_files:
            version = _extract_version(migration_file.name)
            exists = connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = ?",
                (version,),
            ).fetchone()
            if exists:
                continue
            _apply_migration_atomically(
                connection,
                version=version,
                filename=migration_file.name,
                migration_sql=migration_file.read_text(encoding="utf-8"),
            )
            applied_versions.append(version)
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()
    return applied_versions


def init_db(db_path: str | Path) -> list[str]:
    """Create database, apply migrations, and verify runtime schema compatibility."""
    applied_versions = migrate(db_path)
    validate_schema_compatibility(db_path)
    return applied_versions


def build_sqlite_engine(db_path: str | Path) -> Engine:
    """Build SQLAlchemy engine for a SQLite file database."""
    resolved = _resolve_db_path(db_path)
    validate_schema_compatibility(resolved)
    engine = create_engine(URL.create(drivername="sqlite+pysqlite", database=str(resolved)))

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: sqlite3.Connection, _: object) -> None:
        cursor = dbapi_connection.cursor()
        for pragma in _SQLITE_PRAGMAS:
            cursor.execute(pragma)
        cursor.close()

    return engine


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Provide transactional session scope."""
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

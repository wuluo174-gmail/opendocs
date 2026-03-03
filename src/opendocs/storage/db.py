"""Database initialization and migration helpers for SQLite."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

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


def _connect_sqlite(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _apply_migration_atomically(
    connection: sqlite3.Connection,
    *,
    version: str,
    filename: str,
    migration_sql: str,
) -> None:
    applied_at = datetime.now(UTC).isoformat()
    script = (
        "BEGIN IMMEDIATE;\n"
        f"{migration_sql}\n"
        "INSERT INTO schema_migrations (version, filename, applied_at) VALUES "
        f"({_sql_literal(version)}, {_sql_literal(filename)}, {_sql_literal(applied_at)});\n"
        "COMMIT;\n"
    )
    try:
        connection.executescript(script)
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise


def migrate(db_path: str | Path) -> list[str]:
    """Apply pending schema SQL files in order and return applied versions."""
    resolved = _resolve_db_path(db_path)
    applied_versions: list[str] = []
    connection = _connect_sqlite(resolved)
    try:
        connection.execute(_MIGRATION_TABLE_SQL)
        connection.commit()
        for migration_file in _list_migration_files():
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


def init_db(db_path: str | Path) -> None:
    """Create database and apply all migrations."""
    migrate(db_path)


def build_sqlite_engine(db_path: str | Path) -> Engine:
    """Build SQLAlchemy engine for a SQLite file database."""
    resolved = _resolve_db_path(db_path)
    engine = create_engine(URL.create(drivername="sqlite+pysqlite", database=str(resolved)))

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: sqlite3.Connection, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
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

"""Schema consistency test: ORM models vs SQL migration path.

Verifies that every table declared in the ORM (Base.metadata) is also
created by the migration pipeline (init_db / migrate), and that columns
match between ORM and SQL. This prevents ORM-only constraints from drifting
away from the real SQLite schema.

One-way check (ORM → migrations) is intentional:
- schema_migrations: migration-system table, not in ORM by design.
- chunk_fts: FTS5 virtual table, not declarable in SQLAlchemy ORM by design.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from pathlib import Path

from opendocs.domain.models import Base
from opendocs.storage.db import init_db
from opendocs.utils.path_facts import (
    build_display_path,
    derive_directory_facts,
    derive_source_display_root,
)


def test_all_orm_tables_exist_after_migrations(db_path: Path) -> None:
    """Every ORM-declared table must be present after running all migrations."""
    init_db(db_path)

    connection = sqlite3.connect(db_path)
    try:
        migration_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
        }
    finally:
        connection.close()

    orm_tables = {table.name for table in Base.metadata.sorted_tables}

    missing = orm_tables - migration_tables
    assert not missing, (
        f"ORM tables not created by migrations: {sorted(missing)}. "
        "Add a new migration file to create them, or remove from ORM if unused."
    )


def test_orm_columns_match_migration_columns(db_path: Path) -> None:
    """Every column in ORM models must exist in the migrated DB with matching name and NOT NULL."""
    init_db(db_path)

    connection = sqlite3.connect(db_path)
    try:
        for table in Base.metadata.sorted_tables:
            rows = connection.execute(f"PRAGMA table_info({table.name})").fetchall()
            if not rows:
                # Table missing entirely — caught by test_all_orm_tables_exist
                continue

            # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
            db_columns = {row[1]: {"notnull": bool(row[3]), "pk": bool(row[5])} for row in rows}

            for col in table.columns:
                assert col.name in db_columns, (
                    f"ORM column {table.name}.{col.name} missing in migrated DB. "
                    "Add it to the migration SQL or remove from ORM."
                )

                db_info = db_columns[col.name]
                # Primary keys are implicitly NOT NULL in SQLite
                orm_not_null = not col.nullable or db_info["pk"]
                db_not_null = db_info["notnull"] or db_info["pk"]

                assert orm_not_null == db_not_null, (
                    f"Nullability mismatch for {table.name}.{col.name}: "
                    f"ORM nullable={col.nullable}, DB notnull={db_info['notnull']}"
                )
    finally:
        connection.close()


def test_orm_indexes_match_migration_indexes(db_path: Path) -> None:
    """Every ORM-declared index must exist in the migrated DB with matching columns."""
    init_db(db_path)

    connection = sqlite3.connect(db_path)
    try:
        # Collect all explicit indexes from sqlite_master (exclude autoindex)
        rows = connection.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'index' AND name NOT LIKE 'sqlite_autoindex_%'"
        ).fetchall()

        # Parse index columns from CREATE INDEX sql: ... ON table (col1, col2, ...)
        # Partial indexes end with a WHERE clause, so the column list must be
        # extracted from the ON (...) segment instead of the SQL tail.
        db_indexes: dict[str, list[str]] = {}
        col_pattern = re.compile(r"ON\s+\w+\s*\(([^)]+)\)", re.IGNORECASE)
        for name, sql in rows:
            if sql is None:
                continue
            match = col_pattern.search(sql)
            if match:
                cols = [c.strip().strip('"') for c in match.group(1).split(",")]
                db_indexes[name] = cols

        # Build a set of (table_name, tuple(columns)) from DB indexes
        db_index_by_table: dict[str, set[tuple[str, ...]]] = {}
        table_pattern = re.compile(r"ON\s+(\w+)\s*\(", re.IGNORECASE)
        for name, sql in rows:
            if sql is None:
                continue
            table_match = table_pattern.search(sql)
            col_match = col_pattern.search(sql)
            if table_match and col_match:
                tbl = table_match.group(1)
                cols = tuple(c.strip().strip('"') for c in col_match.group(1).split(","))
                db_index_by_table.setdefault(tbl, set()).add(cols)

        # Verify every ORM-declared index has a matching DB index (by table + columns)
        for table in Base.metadata.sorted_tables:
            for index in table.indexes:
                orm_cols = tuple(col.name for col in index.columns)
                db_cols_set = db_index_by_table.get(table.name, set())
                assert orm_cols in db_cols_set, (
                    f"ORM index {index.name} on {table.name}{list(orm_cols)} "
                    f"has no matching DB index. DB indexes on {table.name}: "
                    f"{[list(c) for c in db_cols_set]}. "
                    "Add it to the migration SQL."
                )
    finally:
        connection.close()


def test_orm_foreign_keys_match_migration_foreign_keys(db_path: Path) -> None:
    """Every ORM foreign key must exist in the migrated DB with matching target."""
    init_db(db_path)

    connection = sqlite3.connect(db_path)
    try:
        for table in Base.metadata.sorted_tables:
            db_foreign_keys = {
                (row[3], row[2], row[4], row[6])
                for row in connection.execute(f"PRAGMA foreign_key_list({table.name})").fetchall()
            }
            orm_foreign_keys = {
                (
                    fk.parent.name,
                    fk.column.table.name,
                    fk.column.name,
                    fk.ondelete or "NO ACTION",
                )
                for fk in table.foreign_keys
            }
            assert orm_foreign_keys == db_foreign_keys, (
                f"Foreign key mismatch for {table.name}: "
                f"ORM={sorted(orm_foreign_keys)} DB={sorted(db_foreign_keys)}. "
                "Sync models.py and migration SQL."
            )
    finally:
        connection.close()


def test_orm_check_constraint_count_matches_db(db_path: Path) -> None:
    """ORM and SQL must declare the same number of CHECK constraints per table.

    SQLite inline CHECK constraints don't carry names, so we compare counts
    rather than names. This catches the most common drift: adding a CHECK in
    ORM but forgetting the corresponding SQL (or vice versa).
    """
    init_db(db_path)

    check_pattern = re.compile(r"\bCHECK\s*\(", re.IGNORECASE)

    connection = sqlite3.connect(db_path)
    try:
        table_sql: dict[str, str] = {}
        for row in connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table' AND sql IS NOT NULL"
        ).fetchall():
            table_sql[row[0]] = row[1]

        for table in Base.metadata.sorted_tables:
            from sqlalchemy import CheckConstraint as _CK

            orm_checks = [c for c in table.constraints if isinstance(c, _CK) and c.name]
            sql = table_sql.get(table.name, "")
            db_check_count = len(check_pattern.findall(sql))

            assert len(orm_checks) == db_check_count, (
                f"CHECK constraint count mismatch for '{table.name}': "
                f"ORM declares {len(orm_checks)} named CHECK constraints, "
                f"but migration SQL has {db_check_count} CHECK clauses. "
                "Sync models.py and 0001_initial.sql."
            )
    finally:
        connection.close()


def test_orm_and_raw_sql_timestamp_format_consistency(db_path: Path) -> None:
    """ORM path and raw SQL DEFAULT path must produce comparable timestamps.

    ORM writes via utcnow_naive() produce 'YYYY-MM-DD HH:MM:SS.ffffff'.
    SQL DEFAULT (datetime('now')) produces 'YYYY-MM-DD HH:MM:SS'.
    Both must parse back correctly and sort consistently.
    """
    import sqlite3 as _sqlite3

    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session

    from opendocs.domain.models import FileOperationPlanModel

    init_db(db_path)

    engine = create_engine(f"sqlite+pysqlite:///{db_path}")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys = ON")

    # Write via ORM
    orm_plan_id = str(uuid.uuid4())
    with Session(engine) as session:
        plan = FileOperationPlanModel(
            plan_id=orm_plan_id,
            operation_type="move",
            status="draft",
            item_count=0,
            risk_level="low",
            preview_json={},
        )
        session.add(plan)
        session.commit()

    # Write via raw SQL (relies on DEFAULT)
    raw_plan_id = str(uuid.uuid4())
    conn = _sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO file_operation_plans (plan_id, operation_type, item_count, preview_json) "
        "VALUES (?, 'create', 0, '{}')",
        (raw_plan_id,),
    )
    conn.commit()

    # Read both timestamps via raw SQL
    rows = conn.execute(
        "SELECT plan_id, created_at FROM file_operation_plans WHERE plan_id IN (?, ?) "
        "ORDER BY created_at",
        (orm_plan_id, raw_plan_id),
    ).fetchall()
    conn.close()

    assert len(rows) == 2
    for plan_id, ts in rows:
        # Both formats must start with YYYY-MM-DD HH:MM:SS
        assert len(ts) >= 19, f"Timestamp too short for {plan_id}: {ts!r}"
        assert ts[4] == "-" and ts[10] == " " and ts[13] == ":", (
            f"Unexpected timestamp format for {plan_id}: {ts!r}"
        )


def test_fts_trigger_syncs_chunks_to_chunk_fts(db_path: Path) -> None:
    """FTS triggers must keep chunk_fts in sync on INSERT, UPDATE, and DELETE."""
    init_db(db_path)

    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        # Insert a document first (required by FK)
        doc_id = str(uuid.uuid4())
        source_root_id = str(uuid.uuid4())
        connection.execute(
            "INSERT INTO source_roots (source_root_id, path, display_root, label, "
            "exclude_rules_json, recursive, is_active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source_root_id,
                "/test",
                derive_source_display_root("/test", source_root_id=source_root_id),
                "test source",
                "{}",
                1,
                1,
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
            ),
        )
        connection.execute(
            "INSERT INTO documents (doc_id, path, relative_path, display_path, "
            "directory_path, relative_directory_path, source_root_id, source_path, "
            "hash_sha256, title, file_type, size_bytes, created_at, modified_at, "
            "parse_status, tags_json, sensitivity, is_deleted_from_fs) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                doc_id,
                f"/test/{doc_id}.md",
                f"{doc_id}.md",
                build_display_path("test", f"{doc_id}.md"),
                derive_directory_facts(f"/test/{doc_id}.md", f"{doc_id}.md")[0],
                derive_directory_facts(f"/test/{doc_id}.md", f"{doc_id}.md")[1],
                source_root_id,
                f"/test/{doc_id}.md",
                "a" * 64,
                "Test Doc",
                "md",
                100,
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
                "success",
                "[]",
                "internal",
                0,
            ),
        )

        # INSERT trigger: insert a chunk and verify FTS has it
        chunk_id = str(uuid.uuid4())
        connection.execute(
            "INSERT INTO chunks (chunk_id, doc_id, chunk_index, text, char_start, char_end) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (chunk_id, doc_id, 0, "hello world searchable content", 0, 30),
        )
        connection.commit()

        fts_result = connection.execute(
            "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'searchable'"
        ).fetchall()
        assert len(fts_result) == 1
        assert fts_result[0][0] == chunk_id

        # UPDATE trigger: update chunk text, old term gone, new term found
        connection.execute(
            "UPDATE chunks SET text = 'updated replacement text' WHERE chunk_id = ?",
            (chunk_id,),
        )
        connection.commit()

        old_match = connection.execute(
            "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'searchable'"
        ).fetchall()
        assert len(old_match) == 0, "Old text should not match after UPDATE"

        new_match = connection.execute(
            "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'replacement'"
        ).fetchall()
        assert len(new_match) == 1
        assert new_match[0][0] == chunk_id

        # DELETE trigger: delete chunk, FTS should be empty
        connection.execute("DELETE FROM chunks WHERE chunk_id = ?", (chunk_id,))
        connection.commit()

        after_delete = connection.execute(
            "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'replacement'"
        ).fetchall()
        assert len(after_delete) == 0, "FTS should be empty after DELETE"
    finally:
        connection.close()

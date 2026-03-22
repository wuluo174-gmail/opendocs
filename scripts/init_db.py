"""Initialize OpenDocs SQLite database for S1."""

from __future__ import annotations

import argparse
from pathlib import Path

from opendocs.exceptions import SchemaCompatibilityError
from opendocs.storage.db import init_db


def run_init_db(db_path: str | Path) -> list[str]:
    return init_db(db_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize OpenDocs SQLite database")
    parser.add_argument(
        "--db-path",
        required=True,
        type=Path,
        help="SQLite database path",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        applied = run_init_db(args.db_path)
    except SchemaCompatibilityError as exc:
        print(f"schema error: {exc}")
        return 2
    if applied:
        print(f"database initialized at {args.db_path} (applied: {', '.join(applied)})")
    else:
        print(f"database initialized at {args.db_path} (no pending migrations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Rebuild index for a given source directory.

Gate command: python scripts/rebuild_index.py --source tests/fixtures/generated/corpus_main
Always calls IndexService.rebuild_index() (force=True, S3-T04 path).
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rebuild document index.")
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Source directory to index",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Path to SQLite database (default: temp file)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    source_path: Path = args.source.resolve()
    if not source_path.is_dir():
        print(f"error: source path does not exist or is not a directory: {source_path}")
        return 2

    # Lazy imports to keep CLI startup fast
    from opendocs.app.index_service import IndexService
    from opendocs.app.source_service import SourceService
    from opendocs.exceptions import SchemaCompatibilityError
    from opendocs.storage.db import build_sqlite_engine, init_db
    from opendocs.utils.logging import init_logging

    # Resolve DB path
    if args.db_path:
        db_path = args.db_path.resolve()
    else:
        db_path = Path(tempfile.mkdtemp()) / "opendocs_rebuild.db"

    # Set up logging
    log_dir = db_path.parent / "logs"
    init_logging(log_dir)

    # Initialize database
    try:
        init_db(db_path)
        engine = build_sqlite_engine(db_path)
    except SchemaCompatibilityError as exc:
        print(f"schema error: {exc}")
        return 2

    # Set up HNSW path
    hnsw_path = db_path.parent / "index" / "hnsw" / "vectors.bin"
    hnsw_path.parent.mkdir(parents=True, exist_ok=True)

    # Add source (idempotent)
    source_service = SourceService(engine)
    source = source_service.add_source(source_path)

    # Fixed: always call rebuild_index (S3-T04 path)
    index_service = IndexService(engine, hnsw_path=hnsw_path)
    result = index_service.rebuild_index(source.source_root_id)

    # Output summary
    print(
        f"Rebuild complete: {result.success_count} success, "
        f"{result.failed_count} failed, {result.skipped_count} skipped, "
        f"hnsw={result.hnsw_status}, duration={result.duration_sec:.1f}s"
    )

    # TC-002: individual file failures are expected and recorded, not crash-worthy.
    # Return 0 if at least some files succeeded; return 1 only if zero succeeded.
    if result.success_count == 0 and result.total > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Canonical runtime path ownership for one OpenDocs runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_DEFAULT_DB_FILENAME = "opendocs.db"
_DEFAULT_HNSW_FILENAME = "chunks.hnsw"


@dataclass(frozen=True)
class RuntimePaths:
    """Single source of truth for mutable runtime paths."""

    app_root: Path
    runtime_root: Path
    db_path: Path
    hnsw_path: Path


def resolve_runtime_root_from_db_path(db_path: str | Path) -> Path:
    """Collapse one SQLite db path into the owning runtime root."""
    resolved_db_path = Path(db_path).expanduser().resolve()
    if resolved_db_path.parent.name == "data":
        return resolved_db_path.parent.parent
    return resolved_db_path.parent


def resolve_runtime_hnsw_path(runtime_root: str | Path) -> Path:
    """Return the canonical HNSW artifact path under one runtime root."""
    return (
        Path(runtime_root).expanduser().resolve() / "index" / "hnsw" / _DEFAULT_HNSW_FILENAME
    )


def build_runtime_paths(
    *,
    app_root: str | Path,
    db_path: str | Path | None = None,
    hnsw_path: str | Path | None = None,
) -> RuntimePaths:
    """Build one canonical runtime path bundle.

    Config discovery still belongs to ``app_root``. Mutable runtime state belongs
    to the runtime root derived from the database path, so ``--db`` becomes the
    owner for sibling runtime artifacts unless ``--hnsw`` overrides that one
    specific path explicitly.
    """

    resolved_app_root = Path(app_root).expanduser().resolve()
    resolved_db_path = (
        Path(db_path).expanduser().resolve()
        if db_path is not None
        else resolved_app_root / "data" / _DEFAULT_DB_FILENAME
    )
    runtime_root = resolve_runtime_root_from_db_path(resolved_db_path)
    resolved_hnsw_path = (
        Path(hnsw_path).expanduser().resolve()
        if hnsw_path is not None
        else resolve_runtime_hnsw_path(runtime_root)
    )
    return RuntimePaths(
        app_root=resolved_app_root,
        runtime_root=runtime_root,
        db_path=resolved_db_path,
        hnsw_path=resolved_hnsw_path,
    )

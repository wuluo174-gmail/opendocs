"""Helpers for deriving normalized source/document path facts."""

from __future__ import annotations

import re
from collections.abc import Collection
from pathlib import PurePosixPath

_WINDOWS_DRIVE_ROOT_RE = re.compile(r"^[A-Za-z]:/$")


def normalize_path_separators(value: str) -> str:
    """Normalize path separators for DB-backed filtering and comparisons."""
    return value.replace("\\", "/")


def normalize_directory_prefix(value: str) -> str:
    """Normalize a directory filter prefix while preserving absolute roots."""
    normalized = normalize_path_separators(value).strip()
    if normalized in {"", "/"} or _WINDOWS_DRIVE_ROOT_RE.fullmatch(normalized):
        return normalized
    return normalized.rstrip("/")


def build_directory_prefix_patterns(prefix: str) -> tuple[str, str]:
    """Return exact prefix and escaped descendant LIKE pattern for SQLite."""
    normalized = normalize_directory_prefix(prefix)
    escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    if normalized == "/":
        like_pattern = "/%"
    elif _WINDOWS_DRIVE_ROOT_RE.fullmatch(normalized):
        like_pattern = f"{escaped}%"
    else:
        like_pattern = f"{escaped}/%"

    return normalized, like_pattern


def derive_directory_facts(path: str, relative_path: str) -> tuple[str, str]:
    """Return (absolute_directory_path, relative_directory_path)."""

    normalized_path = normalize_path_separators(path).strip()
    normalized_relative_path = normalize_path_separators(relative_path).strip("/")

    if "/" not in normalized_relative_path:
        relative_directory_path = ""
    else:
        relative_directory_path = normalized_relative_path.rsplit("/", 1)[0]

    last_sep = normalized_path.rfind("/")
    if last_sep < 0:
        directory_path = normalized_path
    elif last_sep == 0:
        directory_path = "/"
    elif last_sep == 2 and len(normalized_path) >= 3 and normalized_path[1] == ":":
        directory_path = normalized_path[:3]
    else:
        directory_path = normalized_path[:last_sep]

    return directory_path, relative_directory_path


def derive_source_display_root(
    path: str,
    *,
    source_root_id: str,
    occupied_roots: Collection[str] = (),
) -> str:
    """Return a stable, human-readable root label for one source root.

    The display root is owned by the source root itself, not reconstructed by
    search/UI layers from absolute paths. Basenames stay readable; collisions
    are disambiguated with the immutable source_root_id prefix.
    """

    normalized_path = normalize_path_separators(path).strip()
    if normalized_path == "/":
        candidate = "root"
    elif _looks_like_windows_drive_root(normalized_path):
        candidate = f"{normalized_path[0].lower()}-drive"
    else:
        trimmed_path = normalized_path.rstrip("/")
        candidate = PurePosixPath(trimmed_path).name or "source"

    if candidate not in occupied_roots:
        return candidate
    return f"{candidate}__{source_root_id.split('-', 1)[0]}"


def build_display_path(display_root: str, relative_path: str) -> str:
    """Return the human-facing document path shown in search/citation UIs."""

    normalized_root = normalize_path_separators(display_root).strip().strip("/")
    normalized_relative_path = normalize_path_separators(relative_path).strip().strip("/")
    if not normalized_root:
        raise ValueError("display_root must not be empty")
    if not normalized_relative_path:
        return normalized_root
    return f"{normalized_root}/{normalized_relative_path}"


def _looks_like_windows_drive_root(path: str) -> bool:
    candidate = path if path.endswith("/") else f"{path}/"
    return _WINDOWS_DRIVE_ROOT_RE.fullmatch(candidate) is not None

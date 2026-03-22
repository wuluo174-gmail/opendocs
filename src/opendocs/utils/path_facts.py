"""Helpers for deriving normalized directory facts from document paths."""

from __future__ import annotations

import re

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

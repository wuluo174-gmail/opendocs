"""Filesystem scanner with structured exclude rules."""

from __future__ import annotations

import logging
import os
import platform
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ExcludeRules(BaseModel):
    """Structured exclude rules (spec §10.1 FR-001)."""

    ignore_hidden: bool = True
    exclude_dirs: list[str] = Field(default_factory=lambda: ["__pycache__", ".git"])
    exclude_globs: list[str] = Field(default_factory=list)
    max_size_bytes: int | None = None

    def should_exclude_dir(self, dir_name: str) -> bool:
        if self.ignore_hidden and dir_name.startswith("."):
            return True
        return dir_name in self.exclude_dirs

    def should_exclude_file(self, file_name: str, size_bytes: int) -> bool:
        import fnmatch

        if self.ignore_hidden and file_name.startswith("."):
            return True
        for pattern in self.exclude_globs:
            if fnmatch.fnmatch(file_name, pattern):
                return True
        if self.max_size_bytes is not None and size_bytes > self.max_size_bytes:
            return True
        return False


def _get_file_birth_time(stat_result: os.stat_result) -> datetime:
    """Get file creation time, cross-platform.

    - macOS/FreeBSD: st_birthtime (accurate)
    - Windows: st_ctime (accurate, is creation time)
    - Linux: min(st_ctime, st_mtime) as approximation (ctime is inode change time)
    """
    if hasattr(stat_result, "st_birthtime"):
        return datetime.fromtimestamp(stat_result.st_birthtime)
    elif platform.system() == "Windows":
        return datetime.fromtimestamp(stat_result.st_ctime)
    else:
        return datetime.fromtimestamp(min(stat_result.st_ctime, stat_result.st_mtime))


def _derive_file_identity(stat_result: os.stat_result) -> str | None:
    """Best-effort stable identity for rename/move reconciliation.

    ``st_dev`` + ``st_ino`` stays stable across renames within the same
    filesystem. If the platform cannot provide a meaningful inode, fall back
    to ``None`` and let callers use path-based behavior.
    """
    inode = getattr(stat_result, "st_ino", 0)
    device = getattr(stat_result, "st_dev", 0)
    try:
        inode_int = int(inode)
        device_int = int(device)
    except (TypeError, ValueError):
        return None
    if inode_int <= 0:
        return None
    return f"{device_int}:{inode_int}"


# Extension to file_type mapping
_EXT_TO_TYPE: dict[str, str] = {
    ".txt": "txt",
    ".md": "md",
    ".docx": "docx",
    ".pdf": "pdf",
}


@dataclass
class ScannedFile:
    """A single file discovered during a scan."""

    path: Path
    relative_path: str
    size_bytes: int
    created_at: datetime
    modified_at: datetime
    file_identity: str | None
    file_type: str  # txt/md/docx/pdf/unsupported


@dataclass
class ScanResult:
    """Aggregated result of scanning a source root."""

    source_root_id: str
    source_root_path: str
    included: list[ScannedFile] = field(default_factory=list)
    excluded_paths: list[str] = field(default_factory=list)
    unsupported_paths: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    duration_sec: float = 0.0

    @property
    def included_count(self) -> int:
        return len(self.included)

    @property
    def excluded_count(self) -> int:
        return len(self.excluded_paths)

    @property
    def unsupported_count(self) -> int:
        return len(self.unsupported_paths)

    @property
    def error_count(self) -> int:
        return len(self.errors)


class Scanner:
    """Walk a source root directory, apply exclude rules, collect file metadata."""

    def __init__(self, registry: Any) -> None:
        """*registry* must have an ``is_supported(path)`` method (ParserRegistry)."""
        self._registry = registry

    def scan(
        self,
        root_path: Path,
        *,
        source_root_id: str,
        exclude_rules: ExcludeRules | None = None,
        recursive: bool = True,
    ) -> ScanResult:
        root_path = Path(root_path).resolve()
        rules = exclude_rules or ExcludeRules()
        start = time.monotonic()
        result = ScanResult(
            source_root_id=source_root_id,
            source_root_path=str(root_path),
        )
        self._walk(root_path, root_path, rules, recursive, result)
        result.duration_sec = time.monotonic() - start
        return result

    def _walk(
        self,
        current: Path,
        root: Path,
        rules: ExcludeRules,
        recursive: bool,
        result: ScanResult,
    ) -> None:
        try:
            entries = list(os.scandir(current))
        except PermissionError:
            result.errors.append((str(current), "permission denied"))
            return
        except OSError as exc:
            result.errors.append((str(current), str(exc)))
            return

        for entry in sorted(entries, key=lambda e: e.name):
            try:
                if entry.is_dir(follow_symlinks=False):
                    if rules.should_exclude_dir(entry.name):
                        continue
                    if recursive:
                        self._walk(Path(entry.path), root, rules, recursive, result)
                    continue

                if not entry.is_file(follow_symlinks=False):
                    continue

                stat = entry.stat(follow_symlinks=False)
                rel_path = str(Path(entry.path).relative_to(root))

                if rules.should_exclude_file(entry.name, stat.st_size):
                    result.excluded_paths.append(rel_path)
                    continue

                ext = Path(entry.name).suffix.lower()
                file_type = _EXT_TO_TYPE.get(ext, "unsupported")

                if file_type == "unsupported" or not self._registry.is_supported(entry.path):
                    result.unsupported_paths.append(rel_path)  # diagnostic
                    result.excluded_paths.append(rel_path)  # FR-001 compliance
                    continue

                scanned = ScannedFile(
                    path=Path(entry.path).resolve(),
                    relative_path=rel_path,
                    size_bytes=stat.st_size,
                    created_at=_get_file_birth_time(stat),
                    modified_at=datetime.fromtimestamp(stat.st_mtime),
                    file_identity=_derive_file_identity(stat),
                    file_type=file_type,
                )
                result.included.append(scanned)

            except PermissionError:
                result.errors.append((str(entry.path), "permission denied"))
            except OSError as exc:
                result.errors.append((str(entry.path), str(exc)))

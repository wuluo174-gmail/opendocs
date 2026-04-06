"""Filesystem scanner with structured exclude rules."""

from __future__ import annotations

import logging
import os
import platform
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ExcludeRules(BaseModel):
    """Structured exclude rules (spec §10.1 FR-001)."""

    ignore_hidden: bool = True
    exclude_dirs: list[str] = Field(default_factory=lambda: ["__pycache__", ".git"])
    exclude_globs: list[str] = Field(default_factory=list)
    max_size_bytes: int | None = None

    def exclusion_reason_for_dir(self, dir_name: str) -> str | None:
        if self.ignore_hidden and dir_name.startswith("."):
            return "hidden_dir"
        if dir_name in self.exclude_dirs:
            return "excluded_dir"
        return None

    def should_exclude_dir(self, dir_name: str) -> bool:
        return self.exclusion_reason_for_dir(dir_name) is not None

    def exclusion_reason_for_file(self, file_name: str, size_bytes: int) -> str | None:
        import fnmatch

        if self.ignore_hidden and file_name.startswith("."):
            return "hidden_file"
        for pattern in self.exclude_globs:
            if fnmatch.fnmatch(file_name, pattern):
                return f"exclude_glob:{pattern}"
        if self.max_size_bytes is not None and size_bytes > self.max_size_bytes:
            return "max_size_bytes"
        return None

    def should_exclude_file(self, file_name: str, size_bytes: int) -> bool:
        return self.exclusion_reason_for_file(file_name, size_bytes) is not None


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


@dataclass(frozen=True)
class ScanDecision:
    """A structured scan decision recorded during traversal."""

    path: str
    kind: Literal["file", "directory"]
    reason: str


@dataclass
class ScanResult:
    """Aggregated result of scanning a source root."""

    source_root_id: str
    source_root_path: str
    included: list[ScannedFile] = field(default_factory=list)
    excluded_entries: list[ScanDecision] = field(default_factory=list)
    unsupported_entries: list[ScanDecision] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    root_error: tuple[str, str] | None = None
    duration_sec: float = 0.0

    @property
    def included_count(self) -> int:
        return len(self.included)

    @property
    def excluded_count(self) -> int:
        return len(self.excluded_entries)

    @property
    def unsupported_count(self) -> int:
        return len(self.unsupported_entries)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def has_root_failure(self) -> bool:
        return self.root_error is not None

    @property
    def excluded_paths(self) -> list[str]:
        return [entry.path for entry in self.excluded_entries]

    @property
    def unsupported_paths(self) -> list[str]:
        return [entry.path for entry in self.unsupported_entries]

    def record_excluded(
        self,
        path: str,
        *,
        kind: Literal["file", "directory"],
        reason: str,
    ) -> None:
        self.excluded_entries.append(
            ScanDecision(
                path=path,
                kind=kind,
                reason=reason,
            )
        )

    def record_unsupported(
        self,
        path: str,
        *,
        kind: Literal["file", "directory"] = "file",
        reason: str = "unsupported_format",
    ) -> None:
        decision = ScanDecision(path=path, kind=kind, reason=reason)
        self.unsupported_entries.append(decision)
        self.excluded_entries.append(decision)


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
        try:
            entries = list(os.scandir(root_path))
        except PermissionError:
            result.root_error = (str(root_path), "permission denied")
        except OSError as exc:
            result.root_error = (str(root_path), str(exc))
        else:
            self._walk_entries(entries, root_path, root_path, rules, recursive, result)
        result.duration_sec = time.monotonic() - start
        return result

    def _walk_entries(
        self,
        entries: list[os.DirEntry[str]],
        current: Path,
        root: Path,
        rules: ExcludeRules,
        recursive: bool,
        result: ScanResult,
    ) -> None:
        for entry in sorted(entries, key=lambda e: e.name):
            try:
                if entry.is_dir(follow_symlinks=False):
                    rel_path = str(Path(entry.path).relative_to(root))
                    exclusion_reason = rules.exclusion_reason_for_dir(entry.name)
                    if exclusion_reason is not None:
                        result.record_excluded(
                            rel_path,
                            kind="directory",
                            reason=exclusion_reason,
                        )
                        continue
                    if recursive:
                        self._walk(Path(entry.path), root, rules, recursive, result)
                    continue

                if not entry.is_file(follow_symlinks=False):
                    continue

                stat = entry.stat(follow_symlinks=False)
                rel_path = str(Path(entry.path).relative_to(root))

                exclusion_reason = rules.exclusion_reason_for_file(entry.name, stat.st_size)
                if exclusion_reason is not None:
                    result.record_excluded(
                        rel_path,
                        kind="file",
                        reason=exclusion_reason,
                    )
                    continue

                ext = Path(entry.name).suffix.lower()
                file_type = _EXT_TO_TYPE.get(ext, "unsupported")

                if file_type == "unsupported" or not self._registry.is_supported(entry.path):
                    result.record_unsupported(rel_path)
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

        self._walk_entries(entries, current, root, rules, recursive, result)

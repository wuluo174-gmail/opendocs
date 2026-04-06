"""Search filter system — directory/category/tag/type/time/sensitivity pre-filter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from opendocs.utils.path_facts import build_directory_prefix_patterns, normalize_directory_prefix


@dataclass
class SearchFilter:
    """Six-dimension search filter per spec §8.3."""

    source_roots: list[str] | None = None
    directory_prefixes: list[str] | None = None
    categories: list[str] | None = None
    tags: list[str] | None = None
    file_types: list[str] | None = None
    time_range: tuple[datetime, datetime] | None = None
    sensitivity_levels: list[str] | None = None

    def __post_init__(self) -> None:
        self.source_roots = self._normalize_paths(self.source_roots)
        self.directory_prefixes = self._normalize_paths(self.directory_prefixes)
        self.categories = self._normalize_tokens(self.categories)
        self.tags = self._normalize_tokens(self.tags)
        self.file_types = self._normalize_tokens(self.file_types)
        self.sensitivity_levels = self._normalize_tokens(self.sensitivity_levels)

    @staticmethod
    def _normalize_tokens(values: list[str] | None) -> list[str] | None:
        if not values:
            return None
        seen: set[str] = set()
        normalized: list[str] = []
        for value in values:
            token = " ".join(value.strip().split()).lower()
            if not token or token in seen:
                continue
            seen.add(token)
            normalized.append(token)
        return normalized or None

    @staticmethod
    def _normalize_paths(values: list[str] | None) -> list[str] | None:
        if not values:
            return None
        seen: set[str] = set()
        normalized: list[str] = []
        for value in values:
            collapsed = " ".join(value.strip().split())
            if not collapsed:
                continue
            path = normalize_directory_prefix(collapsed)
            if not path or path in seen:
                continue
            seen.add(path)
            normalized.append(path)
        return normalized or None


def apply_pre_filter(session: Session, filters: SearchFilter | None) -> set[str] | None:
    """Return set of doc_ids matching filters, or None if no filter applied."""
    if filters is None:
        return None

    clauses: list[str] = []
    params: dict = {}
    clause_idx = 0
    from_clause = "documents AS d"

    if filters.source_roots:
        from_clause = "documents AS d JOIN source_roots AS s ON s.source_root_id = d.source_root_id"
        root_clauses = []
        for source_root in filters.source_roots:
            normalized_root = normalize_directory_prefix(source_root)
            if not normalized_root:
                continue
            path_key = f"root_path_{clause_idx}"
            label_key = f"root_label_{clause_idx}"
            params[path_key] = normalized_root
            params[label_key] = normalized_root
            root_clauses.append(f"(s.path = :{path_key} OR s.display_root = :{label_key})")
            clause_idx += 1
        if root_clauses:
            clauses.append(f"({' OR '.join(root_clauses)})")

    if filters.directory_prefixes:
        directory_clauses = []
        for directory_prefix in filters.directory_prefixes:
            normalized_prefix, like_pattern = build_directory_prefix_patterns(directory_prefix)
            if not normalized_prefix:
                continue
            key = f"dir_{clause_idx}"
            like_key = f"dir_like_{clause_idx}"
            params[key] = normalized_prefix
            params[like_key] = like_pattern
            directory_clauses.append(
                "("
                f"d.directory_path = :{key} OR "
                f"d.directory_path LIKE :{like_key} ESCAPE '\\' OR "
                f"d.relative_directory_path = :{key} OR "
                f"d.relative_directory_path LIKE :{like_key} ESCAPE '\\'"
                ")"
            )
            clause_idx += 1
        if directory_clauses:
            clauses.append(f"({' OR '.join(directory_clauses)})")

    if filters.categories:
        phs = []
        for cat in filters.categories:
            key = f"cat_{clause_idx}"
            phs.append(f":{key}")
            params[key] = cat
            clause_idx += 1
        clauses.append(f"d.category IN ({', '.join(phs)})")

    if filters.file_types:
        phs = []
        for ft in filters.file_types:
            key = f"ft_{clause_idx}"
            phs.append(f":{key}")
            params[key] = ft
            clause_idx += 1
        clauses.append(f"d.file_type IN ({', '.join(phs)})")

    if filters.sensitivity_levels:
        phs = []
        for sl in filters.sensitivity_levels:
            key = f"sl_{clause_idx}"
            phs.append(f":{key}")
            params[key] = sl
            clause_idx += 1
        clauses.append(f"d.sensitivity IN ({', '.join(phs)})")

    if filters.time_range:
        params["time_start"] = filters.time_range[0].strftime("%Y-%m-%d %H:%M:%S")
        params["time_end"] = filters.time_range[1].strftime("%Y-%m-%d %H:%M:%S")
        clauses.append("d.modified_at >= :time_start AND d.modified_at <= :time_end")

    if filters.tags:
        tag_clauses = []
        for tag in filters.tags:
            key = f"tag_{clause_idx}"
            params[key] = tag
            tag_clauses.append(
                f"EXISTS (SELECT 1 FROM json_each(d.tags_json) WHERE value = :{key})"
            )
            clause_idx += 1
        clauses.append(f"({' OR '.join(tag_clauses)})")

    if not clauses:
        return None

    where = " AND ".join(clauses)
    sql = sa_text(f"SELECT d.doc_id FROM {from_clause} WHERE d.is_deleted_from_fs = 0 AND {where}")
    rows = session.execute(sql, params).fetchall()
    return {r[0] for r in rows}

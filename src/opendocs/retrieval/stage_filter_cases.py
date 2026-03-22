"""Stage-scoped filter case assets for S4 retrieval verification."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from opendocs.retrieval.filters import SearchFilter
from opendocs.retrieval.stage_asset_loader import read_stage_asset_text
from opendocs.retrieval.stage_search_corpus import build_s4_search_document_profiles

S4_SEARCH_FILTER_CASES_ASSET_REF = "src/opendocs/retrieval/assets/s4_search_filter_cases.json"


@dataclass(frozen=True)
class StageFilterCase:
    case_id: str
    query: str
    expect_doc: str
    directory_prefixes_relative: tuple[str, ...]
    directory_prefixes_absolute: tuple[str, ...]
    use_primary_source_root: bool
    categories: tuple[str, ...]
    tags: tuple[str, ...]
    file_types: tuple[str, ...]
    sensitivity_levels: tuple[str, ...]
    time_range: tuple[datetime, datetime] | None

    def build_filter(self, *, corpus_dir: Path, primary_source_root_id: str) -> SearchFilter:
        directory_prefixes = list(self.directory_prefixes_relative)
        directory_prefixes.extend(
            str((corpus_dir / relative_path).resolve())
            for relative_path in self.directory_prefixes_absolute
        )
        source_root_ids = [primary_source_root_id] if self.use_primary_source_root else None
        return SearchFilter(
            directory_prefixes=directory_prefixes or None,
            source_root_ids=source_root_ids,
            categories=list(self.categories) or None,
            tags=list(self.tags) or None,
            file_types=list(self.file_types) or None,
            time_range=self.time_range,
            sensitivity_levels=list(self.sensitivity_levels) or None,
        )


@lru_cache(maxsize=1)
def load_s4_search_filter_cases() -> tuple[StageFilterCase, ...]:
    """Load and validate the stage-owned S4 filter cases."""
    payload = json.loads(read_stage_asset_text(S4_SEARCH_FILTER_CASES_ASSET_REF))
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("S4 filter cases must contain a 'cases' list")

    document_profiles = build_s4_search_document_profiles()
    known_directories = {
        profile.relative_directory
        for profile in document_profiles.values()
        if profile.relative_directory
    }
    cases: list[StageFilterCase] = []
    seen_ids: set[str] = set()
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise ValueError("S4 filter cases must be objects")

        case_id = str(raw_case.get("id", "")).strip()
        query = str(raw_case.get("query", "")).strip()
        expect_doc = str(raw_case.get("expect_doc", "")).strip()
        directory_prefixes_relative = _as_string_tuple(raw_case.get("directory_prefixes_relative"))
        directory_prefixes_absolute = _as_string_tuple(raw_case.get("directory_prefixes_absolute"))
        use_primary_source_root = raw_case.get("use_primary_source_root") is True
        categories = _as_string_tuple(raw_case.get("categories"))
        tags = _as_string_tuple(raw_case.get("tags"))
        file_types = _as_string_tuple(raw_case.get("file_types"))
        sensitivity_levels = _as_string_tuple(raw_case.get("sensitivity_levels"))
        time_range = _parse_time_range(raw_case.get("time_range"))

        if not case_id:
            raise ValueError(f"S4 filter case missing id: {raw_case!r}")
        if case_id in seen_ids:
            raise ValueError(f"duplicate S4 filter case id: {case_id}")
        if not query:
            raise ValueError(f"S4 filter case missing query: {case_id}")
        if not expect_doc:
            raise ValueError(f"S4 filter case missing expect_doc: {case_id}")
        expected_profile = document_profiles.get(expect_doc)
        if expected_profile is None:
            raise ValueError(f"S4 filter case references unknown corpus document: {case_id}")
        if not any(
            [
                directory_prefixes_relative,
                directory_prefixes_absolute,
                use_primary_source_root,
                categories,
                tags,
                file_types,
                sensitivity_levels,
                time_range,
            ]
        ):
            raise ValueError(f"S4 filter case missing filters: {case_id}")
        _validate_filter_case_against_expected_document(
            case_id=case_id,
            expected_profile=expected_profile,
            known_directories=known_directories,
            directory_prefixes_relative=directory_prefixes_relative,
            directory_prefixes_absolute=directory_prefixes_absolute,
            categories=categories,
            tags=tags,
            file_types=file_types,
            sensitivity_levels=sensitivity_levels,
            time_range=time_range,
        )

        seen_ids.add(case_id)
        cases.append(
            StageFilterCase(
                case_id=case_id,
                query=query,
                expect_doc=expect_doc,
                directory_prefixes_relative=directory_prefixes_relative,
                directory_prefixes_absolute=directory_prefixes_absolute,
                use_primary_source_root=use_primary_source_root,
                categories=categories,
                tags=tags,
                file_types=file_types,
                sensitivity_levels=sensitivity_levels,
                time_range=time_range,
            )
        )

    if len(cases) != 3:
        raise ValueError(f"S4 filter cases must contain exactly 3 acceptance groups, found {len(cases)}")
    return tuple(cases)


def _as_string_tuple(raw_values: object) -> tuple[str, ...]:
    if raw_values is None:
        return ()
    if not isinstance(raw_values, list):
        raise ValueError(f"S4 filter case lists must be arrays, got: {raw_values!r}")
    values = tuple(str(value).strip() for value in raw_values if str(value).strip())
    return values


def _parse_time_range(raw_range: object) -> tuple[datetime, datetime] | None:
    if raw_range is None:
        return None
    if not isinstance(raw_range, dict):
        raise ValueError("S4 filter case time_range must be an object")
    start = str(raw_range.get("start", "")).strip()
    end = str(raw_range.get("end", "")).strip()
    if not start or not end:
        raise ValueError("S4 filter case time_range requires start and end")
    return (datetime.fromisoformat(start), datetime.fromisoformat(end))


def _validate_filter_case_against_expected_document(
    *,
    case_id: str,
    expected_profile,
    known_directories: set[str],
    directory_prefixes_relative: tuple[str, ...],
    directory_prefixes_absolute: tuple[str, ...],
    categories: tuple[str, ...],
    tags: tuple[str, ...],
    file_types: tuple[str, ...],
    sensitivity_levels: tuple[str, ...],
    time_range: tuple[datetime, datetime] | None,
) -> None:
    if directory_prefixes_relative:
        _validate_directory_filters(
            case_id=case_id,
            expected_path=expected_profile.relative_path,
            known_directories=known_directories,
            prefixes=directory_prefixes_relative,
            field_name="directory_prefixes_relative",
        )
    if directory_prefixes_absolute:
        _validate_directory_filters(
            case_id=case_id,
            expected_path=expected_profile.relative_path,
            known_directories=known_directories,
            prefixes=directory_prefixes_absolute,
            field_name="directory_prefixes_absolute",
        )
    if categories:
        normalized = SearchFilter(categories=list(categories)).categories or []
        if expected_profile.metadata.category not in normalized:
            raise ValueError(f"S4 filter case category drift: {case_id}")
    if tags:
        normalized = SearchFilter(tags=list(tags)).tags or []
        if not set(normalized).intersection(expected_profile.metadata.tags):
            raise ValueError(f"S4 filter case tag drift: {case_id}")
    if file_types:
        normalized = SearchFilter(file_types=list(file_types)).file_types or []
        if expected_profile.file_type not in normalized:
            raise ValueError(f"S4 filter case file_type drift: {case_id}")
    if sensitivity_levels:
        normalized = SearchFilter(sensitivity_levels=list(sensitivity_levels)).sensitivity_levels or []
        if expected_profile.metadata.sensitivity not in normalized:
            raise ValueError(f"S4 filter case sensitivity drift: {case_id}")
    if time_range is not None:
        if expected_profile.modified_at is None:
            raise ValueError(f"S4 filter case time_range references document without owned timestamp: {case_id}")
        if not (time_range[0] <= expected_profile.modified_at <= time_range[1]):
            raise ValueError(f"S4 filter case time_range drift: {case_id}")


def _validate_directory_filters(
    *,
    case_id: str,
    expected_path: str,
    known_directories: set[str],
    prefixes: tuple[str, ...],
    field_name: str,
) -> None:
    for prefix in prefixes:
        if prefix not in known_directories:
            raise ValueError(f"S4 filter case references unknown directory in {field_name}: {case_id}")
    if not any(expected_path == prefix or expected_path.startswith(f"{prefix}/") for prefix in prefixes):
        raise ValueError(f"S4 filter case directory drift: {case_id}")

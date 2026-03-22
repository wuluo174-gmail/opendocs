"""Stage-scoped acceptance capture case assets for S4 verification."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from opendocs.retrieval.stage_golden_queries import load_s4_hybrid_search_queries
from opendocs.retrieval.stage_asset_loader import read_stage_asset_text

S4_ACCEPTANCE_CAPTURE_CASES_ASSET_REF = "src/opendocs/retrieval/assets/s4_acceptance_capture_cases.json"


@dataclass(frozen=True)
class StageTc005CaptureCase:
    slug: str
    query_id: str
    note: str


@dataclass(frozen=True)
class StageTc018CaptureCase:
    slug: str
    locator_kind: str
    query: str
    expected_file_name: str
    note: str


@dataclass(frozen=True)
class StageAcceptanceCaptureCases:
    tc005: tuple[StageTc005CaptureCase, ...]
    tc018: tuple[StageTc018CaptureCase, ...]


@lru_cache(maxsize=1)
def load_s4_acceptance_capture_cases() -> StageAcceptanceCaptureCases:
    """Load and validate the stage-owned S4 acceptance capture cases."""
    payload = json.loads(read_stage_asset_text(S4_ACCEPTANCE_CAPTURE_CASES_ASSET_REF))
    if not isinstance(payload, dict):
        raise ValueError("S4 acceptance capture cases must be an object")
    tc005 = _parse_tc005_cases(payload.get("tc005"))
    tc018 = _parse_tc018_cases(payload.get("tc018"))
    return StageAcceptanceCaptureCases(tc005=tc005, tc018=tc018)


def _parse_tc005_cases(raw_cases: object) -> tuple[StageTc005CaptureCase, ...]:
    if not isinstance(raw_cases, list):
        raise ValueError("S4 TC-005 capture cases must be an array")
    golden_queries = {query.query_id: query for query in load_s4_hybrid_search_queries()}
    seen_slugs: set[str] = set()
    seen_query_ids: set[str] = set()
    cases: list[StageTc005CaptureCase] = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise ValueError("S4 TC-005 capture cases must be objects")
        slug = str(raw_case.get("slug", "")).strip()
        query_id = str(raw_case.get("query_id", "")).strip()
        note = str(raw_case.get("note", "")).strip()
        if not slug:
            raise ValueError("S4 TC-005 capture case missing slug")
        if slug in seen_slugs:
            raise ValueError(f"duplicate S4 TC-005 capture slug: {slug}")
        if not query_id:
            raise ValueError(f"S4 TC-005 capture case missing query_id: {slug}")
        if query_id in seen_query_ids:
            raise ValueError(f"duplicate S4 TC-005 capture query_id: {query_id}")
        golden_query = golden_queries.get(query_id)
        if golden_query is None:
            raise ValueError(f"S4 TC-005 capture case references unknown query_id: {query_id}")
        if golden_query.expect_doc is None or golden_query.expect_empty:
            raise ValueError(f"S4 TC-005 capture case must reference a non-empty match query: {query_id}")
        if not note:
            raise ValueError(f"S4 TC-005 capture case missing note: {slug}")
        seen_slugs.add(slug)
        seen_query_ids.add(query_id)
        cases.append(StageTc005CaptureCase(slug=slug, query_id=query_id, note=note))
    if len(cases) != 2:
        raise ValueError(f"S4 TC-005 capture cases must contain exactly 2 entries, found {len(cases)}")
    return tuple(cases)


def _parse_tc018_cases(raw_cases: object) -> tuple[StageTc018CaptureCase, ...]:
    if not isinstance(raw_cases, list):
        raise ValueError("S4 TC-018 capture cases must be an array")
    seen_slugs: set[str] = set()
    seen_file_names: set[str] = set()
    locator_kinds: set[str] = set()
    cases: list[StageTc018CaptureCase] = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise ValueError("S4 TC-018 capture cases must be objects")
        slug = str(raw_case.get("slug", "")).strip()
        locator_kind = str(raw_case.get("locator_kind", "")).strip()
        query = str(raw_case.get("query", "")).strip()
        expected_file_name = str(raw_case.get("expected_file_name", "")).strip()
        note = str(raw_case.get("note", "")).strip()
        if not slug:
            raise ValueError("S4 TC-018 capture case missing slug")
        if slug in seen_slugs:
            raise ValueError(f"duplicate S4 TC-018 capture slug: {slug}")
        if locator_kind not in {"page", "paragraph"}:
            raise ValueError(f"S4 TC-018 capture case has invalid locator_kind: {slug}")
        if not query:
            raise ValueError(f"S4 TC-018 capture case missing query: {slug}")
        if not expected_file_name:
            raise ValueError(f"S4 TC-018 capture case missing expected_file_name: {slug}")
        if expected_file_name in seen_file_names:
            raise ValueError(f"duplicate S4 TC-018 capture expected_file_name: {expected_file_name}")
        if not note:
            raise ValueError(f"S4 TC-018 capture case missing note: {slug}")
        seen_slugs.add(slug)
        seen_file_names.add(expected_file_name)
        locator_kinds.add(locator_kind)
        cases.append(
            StageTc018CaptureCase(
                slug=slug,
                locator_kind=locator_kind,
                query=query,
                expected_file_name=expected_file_name,
                note=note,
            )
        )
    if len(cases) != 2:
        raise ValueError(f"S4 TC-018 capture cases must contain exactly 2 entries, found {len(cases)}")
    if locator_kinds != {"page", "paragraph"}:
        raise ValueError(f"S4 TC-018 capture cases must cover page and paragraph locators: {sorted(locator_kinds)}")
    return tuple(cases)

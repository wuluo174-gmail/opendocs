"""Unit tests for the stage-owned S4 acceptance capture cases."""

from __future__ import annotations

from opendocs.retrieval.stage_acceptance_capture_cases import load_s4_acceptance_capture_cases
from opendocs.retrieval.stage_golden_queries import load_s4_hybrid_search_queries


class TestStageAcceptanceCaptureCases:
    def test_tc005_capture_cases_reference_stage_golden_queries(self) -> None:
        capture_cases = load_s4_acceptance_capture_cases()
        golden_query_ids = {query.query_id for query in load_s4_hybrid_search_queries()}
        assert len(capture_cases.tc005) == 2
        assert {case.query_id for case in capture_cases.tc005}.issubset(golden_query_ids)

    def test_tc018_capture_cases_cover_page_and_paragraph_locators(self) -> None:
        capture_cases = load_s4_acceptance_capture_cases()
        assert len(capture_cases.tc018) == 2
        assert {case.locator_kind for case in capture_cases.tc018} == {"page", "paragraph"}
        assert len({case.expected_file_name for case in capture_cases.tc018}) == 2

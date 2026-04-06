"""Unit tests for the stage-owned S4 filter cases."""

from __future__ import annotations

from pathlib import Path

from opendocs.retrieval.stage_filter_cases import load_s4_search_filter_cases
from opendocs.retrieval.stage_search_corpus import (
    build_s4_search_document_profiles,
    list_s4_search_corpus_documents,
)


class TestStageFilterCases:
    def test_filter_cases_cover_required_acceptance_groups(self) -> None:
        cases = load_s4_search_filter_cases()
        assert len(cases) == 3
        assert {case.case_id for case in cases} == {"S4-FC-001", "S4-FC-002", "S4-FC-003"}

    def test_filter_cases_reference_stage_search_corpus_documents(self) -> None:
        corpus_documents = set(list_s4_search_corpus_documents())
        for case in load_s4_search_filter_cases():
            assert case.expect_doc in corpus_documents

    def test_filter_cases_align_with_expected_document_profiles(self) -> None:
        profiles = build_s4_search_document_profiles()
        case = next(case for case in load_s4_search_filter_cases() if case.case_id == "S4-FC-003")
        profile = profiles[case.expect_doc]
        assert profile.metadata.category == "project"
        assert set(["roadmap", "shared-source"]).issubset(profile.metadata.tags)
        assert profile.metadata.sensitivity == "sensitive"
        assert profile.modified_at is not None

    def test_absolute_directory_case_resolves_from_corpus_root(self, tmp_path: Path) -> None:
        case = next(case for case in load_s4_search_filter_cases() if case.case_id == "S4-FC-002")
        filters = case.build_filter(corpus_dir=tmp_path / "corpus")
        assert filters.directory_prefixes == [
            str((tmp_path / "corpus" / "projects" / "alpha").resolve())
        ]

    def test_combined_case_includes_source_root_path_and_time_range(self, tmp_path: Path) -> None:
        case = next(case for case in load_s4_search_filter_cases() if case.case_id == "S4-FC-003")
        filters = case.build_filter(corpus_dir=tmp_path / "corpus")
        assert filters.source_roots is not None
        assert str((tmp_path / "corpus").resolve()) in filters.source_roots
        assert filters.directory_prefixes is None
        assert filters.categories == ["project"]
        assert filters.tags == ["roadmap", "shared-source"]
        assert filters.sensitivity_levels == ["sensitive"]
        assert filters.time_range is not None

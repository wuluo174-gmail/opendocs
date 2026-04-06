"""Unit tests for the stage-owned S4 search corpus owner."""

from __future__ import annotations

from opendocs.retrieval.stage_search_corpus import (
    build_s4_search_document_profiles,
    build_s4_search_source_defaults,
    list_s4_search_corpus_documents,
)


class TestStageSearchCorpus:
    def test_declares_expected_document_paths(self) -> None:
        documents = list_s4_search_corpus_documents()
        assert documents == (
            "zh_project_plan.md",
            "zh_meeting_notes.md",
            "mixed_tech_report.md",
            "en_project_plan.md",
            "en_weekly_report.txt",
            "projects/alpha/alpha_directory_note.md",
        )

    def test_declares_stage_owned_source_defaults(self) -> None:
        defaults = build_s4_search_source_defaults()
        assert defaults.category == "workspace"
        assert defaults.tags == ["shared-source"]
        assert defaults.sensitivity == "internal"

    def test_builds_effective_document_profiles(self) -> None:
        profiles = build_s4_search_document_profiles()
        project_plan = profiles["zh_project_plan.md"]
        assert project_plan.relative_directory == ""
        assert project_plan.file_type == "md"
        assert project_plan.metadata.category == "project"
        assert project_plan.metadata.tags == ["shared-source", "roadmap", "alpha"]
        assert project_plan.metadata.sensitivity == "sensitive"

    def test_profiles_are_returned_as_isolated_copies(self) -> None:
        profiles = build_s4_search_document_profiles()
        profiles["zh_project_plan.md"].metadata.tags.append("polluted")

        fresh_profiles = build_s4_search_document_profiles()

        assert fresh_profiles["zh_project_plan.md"].metadata.tags == [
            "shared-source",
            "roadmap",
            "alpha",
        ]

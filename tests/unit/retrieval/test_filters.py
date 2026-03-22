"""Unit tests for SearchFilter and apply_pre_filter."""

from opendocs.retrieval.filters import SearchFilter
from opendocs.utils.path_facts import (
    build_directory_prefix_patterns,
    derive_directory_facts,
    normalize_directory_prefix,
)


class TestSearchFilter:
    def test_default_all_none(self) -> None:
        f = SearchFilter()
        assert f.directory_prefixes is None
        assert f.source_root_ids is None
        assert f.categories is None
        assert f.tags is None
        assert f.file_types is None
        assert f.time_range is None
        assert f.sensitivity_levels is None

    def test_file_types_filter(self) -> None:
        f = SearchFilter(file_types=["md", "txt"])
        assert f.file_types == ["md", "txt"]

    def test_combined_filters(self) -> None:
        f = SearchFilter(
            file_types=["md"],
            sensitivity_levels=["public", "internal"],
        )
        assert f.file_types == ["md"]
        assert f.sensitivity_levels == ["public", "internal"]

    def test_filters_are_normalized_and_deduplicated(self) -> None:
        f = SearchFilter(
            categories=[" Project ", "project"],
            tags=[" Roadmap ", "ROADMAP", "Alpha"],
            file_types=[" MD ", "md"],
            sensitivity_levels=[" Sensitive ", "sensitive"],
        )
        assert f.categories == ["project"]
        assert f.tags == ["roadmap", "alpha"]
        assert f.file_types == ["md"]
        assert f.sensitivity_levels == ["sensitive"]

    def test_directory_prefix_normalization_preserves_root(self) -> None:
        assert normalize_directory_prefix("projects/alpha/") == "projects/alpha"
        assert normalize_directory_prefix("/tmp/corpus/") == "/tmp/corpus"
        assert normalize_directory_prefix("C:/") == "C:/"

    def test_derive_directory_facts_uses_normalized_separators(self) -> None:
        assert derive_directory_facts(
            "/tmp/corpus/projects/alpha/file.md",
            "projects/alpha/file.md",
        ) == ("/tmp/corpus/projects/alpha", "projects/alpha")
        assert derive_directory_facts("C:\\docs\\file.md", "file.md") == ("C:/docs", "")

    def test_directory_prefix_patterns_escape_like_metacharacters(self) -> None:
        assert build_directory_prefix_patterns("projects/a_b%c") == (
            "projects/a_b%c",
            "projects/a\\_b\\%c/%",
        )
        assert build_directory_prefix_patterns("/") == ("/", "/%")
        assert build_directory_prefix_patterns("C:/") == ("C:/", "C:/%")

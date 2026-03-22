"""Unit tests for the packaged S4 query lexicon asset."""

from __future__ import annotations

import pytest

from opendocs.retrieval.query_lexicon import (
    build_stage_query_expansion_index,
    build_stage_query_lexicon_index,
    load_stage_query_lexicon,
    normalize_query_lookup_key,
    normalize_query_text,
    parse_query_expansion_index,
    parse_query_lexicon_entries,
)


class TestStageQueryLexicon:
    def test_stage_query_lexicon_has_unique_ids(self) -> None:
        entries = load_stage_query_lexicon()
        ids = [entry.lexicon_id for entry in entries]
        assert len(ids) == len(set(ids))

    def test_stage_query_lexicon_index_resolves_expected_entry(self) -> None:
        lexicon = build_stage_query_lexicon_index()
        assert lexicon["roadmap"].trigger_query == "roadmap"
        assert lexicon["roadmap"].expansions == ("Project Plan", "milestones")

    def test_stage_query_expansion_index_uses_normalized_lookup_key(self) -> None:
        expansions = build_stage_query_expansion_index()
        assert expansions[normalize_query_lookup_key("NLP")] == ("自然语言处理",)
        assert expansions[normalize_query_lookup_key("进展汇报")] == ("项目进度", "项目计划书")

    def test_query_text_normalization_matches_lookup_key_semantics(self) -> None:
        assert normalize_query_text(" ＮＬＰ ") == "NLP"
        assert normalize_query_lookup_key(" ＮＬＰ ") == normalize_query_lookup_key("NLP")

    def test_parse_rejects_duplicate_trigger_after_normalization(self) -> None:
        with pytest.raises(ValueError, match="duplicate stage query trigger after normalization"):
            parse_query_lexicon_entries(
                [
                    {
                        "lexicon_id": "latin",
                        "trigger_query": "NLP",
                        "expansions": ["自然语言处理"],
                    },
                    {
                        "lexicon_id": "fullwidth",
                        "trigger_query": "ＮＬＰ",
                        "expansions": ["文本处理"],
                    },
                ]
            )

    def test_parse_rejects_duplicate_expansion_after_normalization(self) -> None:
        with pytest.raises(ValueError, match="duplicate stage query expansion after normalization"):
            parse_query_lexicon_entries(
                [
                    {
                        "lexicon_id": "dup-expansion",
                        "trigger_query": "roadmap",
                        "expansions": ["Project Plan", " Project  Plan ", "Project Plan"],
                    }
                ]
            )

    def test_parse_rejects_casefold_duplicate_expansion_after_normalization(self) -> None:
        with pytest.raises(ValueError, match="duplicate stage query expansion after normalization"):
            parse_query_lexicon_entries(
                [
                    {
                        "lexicon_id": "dup-casefold-expansion",
                        "trigger_query": "roadmap",
                        "expansions": ["AI", "ai"],
                    }
                ]
            )

    def test_parse_rejects_expansion_that_duplicates_trigger_after_normalization(self) -> None:
        with pytest.raises(ValueError, match="expansion duplicates trigger_query after normalization"):
            parse_query_lexicon_entries(
                [
                    {
                        "lexicon_id": "dup-trigger",
                        "trigger_query": "roadmap",
                        "expansions": [" roadmap ", "milestones"],
                    }
                ]
            )

    def test_parse_expansion_index_rejects_duplicate_trigger_after_normalization(self) -> None:
        with pytest.raises(ValueError, match="duplicate query expansion trigger after normalization"):
            parse_query_expansion_index(
                {
                    "NLP": ["自然语言处理"],
                    "ＮＬＰ": ["文本处理"],
                }
            )

    def test_parse_expansion_index_rejects_empty_expansion_after_normalization(self) -> None:
        with pytest.raises(ValueError, match="has empty expansion"):
            parse_query_expansion_index(
                {
                    "roadmap": ["Project Plan", "  "],
                }
            )

    def test_parse_expansion_index_rejects_expansion_that_duplicates_trigger(self) -> None:
        with pytest.raises(ValueError, match="expansion duplicates trigger_query after normalization"):
            parse_query_expansion_index(
                {
                    "roadmap": [" roadmap ", "milestones"],
                }
            )

    def test_parse_expansion_index_rejects_casefold_duplicate_expansion(self) -> None:
        with pytest.raises(ValueError, match="duplicate query expansion after normalization"):
            parse_query_expansion_index(
                {
                    "roadmap": ["AI", "ai"],
                }
            )

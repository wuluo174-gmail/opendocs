"""Unit tests for the packaged runtime query lexicon asset."""

from __future__ import annotations

import pytest

from opendocs.retrieval.query_lexicon import (
    build_query_expansion_index,
    build_runtime_query_expansion_index,
    build_runtime_query_lexicon_index,
    load_runtime_query_lexicon,
    normalize_query_lookup_key,
    normalize_query_text,
    parse_query_expansion_index,
    parse_query_lexicon_entries,
)


class TestRuntimeQueryLexicon:
    def test_runtime_query_lexicon_has_unique_ids(self) -> None:
        entries = load_runtime_query_lexicon()
        ids = [entry.lexicon_id for entry in entries]
        assert len(ids) == len(set(ids))

    def test_runtime_query_lexicon_index_resolves_expected_entry(self) -> None:
        lexicon = build_runtime_query_lexicon_index()
        assert lexicon["roadmap"].canonical_query == "Project Plan"
        assert lexicon["roadmap"].aliases == ("roadmap", "milestones", "项目路线图")

    def test_runtime_query_expansion_index_uses_symmetric_alias_clusters(self) -> None:
        expansions = build_runtime_query_expansion_index()
        assert expansions[normalize_query_lookup_key("NLP")] == (
            "自然语言处理",
            "language processing",
        )
        assert expansions[normalize_query_lookup_key("身份验证模块")] == (
            "authentication module",
            "login system",
            "登录系统",
            "身份认证模块",
        )

    def test_query_text_normalization_matches_lookup_key_semantics(self) -> None:
        assert normalize_query_text(" ＮＬＰ ") == "NLP"
        assert normalize_query_lookup_key(" ＮＬＰ ") == normalize_query_lookup_key("NLP")

    def test_parse_rejects_duplicate_runtime_term_after_normalization(self) -> None:
        with pytest.raises(ValueError, match="duplicate runtime query term after normalization"):
            parse_query_lexicon_entries(
                [
                    {
                        "lexicon_id": "latin",
                        "canonical_query": "自然语言处理",
                        "aliases": ["NLP"],
                    },
                    {
                        "lexicon_id": "fullwidth",
                        "canonical_query": "文本处理",
                        "aliases": ["ＮＬＰ"],
                    },
                ]
            )

    def test_parse_rejects_duplicate_alias_after_normalization(self) -> None:
        with pytest.raises(ValueError, match="duplicate query alias after normalization"):
            parse_query_lexicon_entries(
                [
                    {
                        "lexicon_id": "dup-alias",
                        "canonical_query": "Project Plan",
                        "aliases": ["roadmap", " roadmap ", "milestones"],
                    }
                ]
            )

    def test_parse_rejects_casefold_duplicate_alias_after_normalization(self) -> None:
        with pytest.raises(ValueError, match="duplicate query alias after normalization"):
            parse_query_lexicon_entries(
                [
                    {
                        "lexicon_id": "dup-casefold-alias",
                        "canonical_query": "artificial intelligence",
                        "aliases": ["AI", "ai"],
                    }
                ]
            )

    def test_parse_rejects_alias_that_duplicates_canonical_after_normalization(self) -> None:
        with pytest.raises(
            ValueError, match="alias duplicates canonical_query after normalization"
        ):
            parse_query_lexicon_entries(
                [
                    {
                        "lexicon_id": "dup-canonical",
                        "canonical_query": "roadmap",
                        "aliases": [" roadmap ", "milestones"],
                    }
                ]
            )

    def test_build_query_expansion_index_expands_all_terms_to_their_peers(self) -> None:
        entries = parse_query_lexicon_entries(
            [
                {
                    "lexicon_id": "auth",
                    "canonical_query": "authentication module",
                    "aliases": ["login system", "身份验证模块"],
                }
            ]
        )
        expansions = build_query_expansion_index(entries)
        assert expansions[normalize_query_lookup_key("authentication module")] == (
            "login system",
            "身份验证模块",
        )
        assert expansions[normalize_query_lookup_key("login system")] == (
            "authentication module",
            "身份验证模块",
        )

    def test_parse_expansion_index_rejects_duplicate_trigger_after_normalization(self) -> None:
        with pytest.raises(
            ValueError, match="duplicate query expansion trigger after normalization"
        ):
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
        with pytest.raises(
            ValueError, match="expansion duplicates trigger_query after normalization"
        ):
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

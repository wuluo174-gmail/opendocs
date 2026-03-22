"""Unit tests for QueryPreprocessor."""

import pytest

from opendocs.retrieval.query_preprocessor import QueryPreprocessor


@pytest.fixture()
def prep() -> QueryPreprocessor:
    return QueryPreprocessor()


class TestNormalization:
    def test_fullwidth_letters(self, prep: QueryPreprocessor) -> None:
        result = prep.prepare("\uff21\uff29")  # ＡＩ
        assert result.raw_normalized == "AI"
        assert result.variants[0].text == "AI"

    def test_fullwidth_digits(self, prep: QueryPreprocessor) -> None:
        result = prep.prepare("\uff12\uff10\uff12\uff14")  # ２０２４
        assert result.raw_normalized == "2024"

    def test_nfc_normalization(self, prep: QueryPreprocessor) -> None:
        result = prep.prepare("cafe\u0301")  # café (decomposed)
        assert "caf" in result.raw_normalized


class TestSanitization:
    def test_strip_unbalanced_quote(self, prep: QueryPreprocessor) -> None:
        result = prep.prepare('hello"world')
        assert result.fts_query is not None
        assert '"' not in result.fts_query  # unbalanced quote stripped

    def test_balanced_quotes_preserved(self, prep: QueryPreprocessor) -> None:
        result = prep.prepare('"exact phrase"')
        assert result.fts_query is not None
        assert '"exact phrase"' == result.fts_query

    def test_strip_unsafe_chars(self, prep: QueryPreprocessor) -> None:
        result = prep.prepare("hello*world^test")
        assert result.fts_query is not None
        assert "*" not in result.fts_query
        assert "^" not in result.fts_query

    def test_preserve_uppercase_or(self, prep: QueryPreprocessor) -> None:
        result = prep.prepare("report OR notes")
        assert result.fts_query == "report OR notes"

    def test_lowercase_or_unchanged(self, prep: QueryPreprocessor) -> None:
        result = prep.prepare("report or notes")
        assert result.fts_query == "report or notes"


class TestEdgeCases:
    def test_empty_raises(self, prep: QueryPreprocessor) -> None:
        with pytest.raises(ValueError, match="empty"):
            prep.prepare("")

    def test_whitespace_raises(self, prep: QueryPreprocessor) -> None:
        with pytest.raises(ValueError, match="empty"):
            prep.prepare("   ")

    def test_raw_normalized_always_set(self, prep: QueryPreprocessor) -> None:
        result = prep.prepare("hello")
        assert result.raw_normalized == "hello"

    def test_cjk_query(self, prep: QueryPreprocessor) -> None:
        result = prep.prepare("项目进度")
        assert result.fts_query is not None
        assert result.raw_normalized == "项目进度"

    def test_mixed_cjk_english(self, prep: QueryPreprocessor) -> None:
        result = prep.prepare("AI 项目")
        assert result.fts_query is not None
        assert result.raw_normalized == "AI 项目"


class TestSynonymExpansion:
    def test_synonym_query_expands_to_canonical_variants(self, prep: QueryPreprocessor) -> None:
        result = prep.prepare("roadmap")
        assert [variant.text for variant in result.variants] == [
            "roadmap",
            "Project Plan",
            "milestones",
        ]
        assert [variant.fts_query for variant in result.variants] == [
            "roadmap",
            "Project Plan",
            "milestones",
        ]

    def test_synonym_lookup_is_case_insensitive_for_latin_queries(
        self,
        prep: QueryPreprocessor,
    ) -> None:
        result = prep.prepare("NLP")
        assert [variant.text for variant in result.variants] == ["NLP", "自然语言处理"]

    def test_custom_expansion_map_rejects_variant_that_duplicates_trigger(self) -> None:
        with pytest.raises(ValueError, match="expansion duplicates trigger_query after normalization"):
            QueryPreprocessor(expansions={"项目进度": (" 项目进度 ", "项目计划书")})

    def test_explicit_empty_expansion_map_disables_default_lexicon(self) -> None:
        prep = QueryPreprocessor(expansions={})
        result = prep.prepare("roadmap")
        assert [variant.text for variant in result.variants] == ["roadmap"]

    def test_custom_expansion_keys_follow_same_normalization_rule(self) -> None:
        prep = QueryPreprocessor(expansions={"ＮＬＰ": ("自然语言处理",)})
        result = prep.prepare("NLP")
        assert [variant.text for variant in result.variants] == ["NLP", "自然语言处理"]

    def test_custom_expansion_map_rejects_duplicate_normalized_keys(self) -> None:
        with pytest.raises(ValueError, match="duplicate query expansion trigger after normalization"):
            QueryPreprocessor(
                expansions={
                    "NLP": ("自然语言处理",),
                    "ＮＬＰ": ("文本处理",),
                }
            )

    def test_custom_expansion_map_rejects_empty_expansion_after_normalization(self) -> None:
        with pytest.raises(ValueError, match="has empty expansion"):
            QueryPreprocessor(expansions={"roadmap": ("Project Plan", " ")})

    def test_custom_expansion_map_rejects_casefold_duplicate_expansions(self) -> None:
        with pytest.raises(ValueError, match="duplicate query expansion after normalization"):
            QueryPreprocessor(expansions={"roadmap": ("AI", "ai")})

"""Unit tests for the stage-owned S4 golden hybrid search queries."""

from __future__ import annotations

from opendocs.retrieval.query_lexicon import build_stage_query_lexicon_index
from opendocs.retrieval.stage_search_corpus import list_s4_search_corpus_documents
from opendocs.retrieval.stage_golden_queries import (
    S4_EXPECTED_LOCATING_QUERY_COUNT,
    S4_EXPECTED_SYNONYM_QUERY_COUNT,
    S4_EXPECTED_ZERO_QUERY_COUNT,
    load_s4_hybrid_search_queries,
)


class TestStageGoldenQueries:
    def test_queries_cover_expected_locating_and_synonym_counts(self) -> None:
        queries = load_s4_hybrid_search_queries()
        assert sum(query.query_type == "locating" for query in queries) == S4_EXPECTED_LOCATING_QUERY_COUNT
        assert sum(query.query_type == "zero" for query in queries) == S4_EXPECTED_ZERO_QUERY_COUNT
        assert sum(query.query_type == "synonym" for query in queries) == S4_EXPECTED_SYNONYM_QUERY_COUNT

    def test_match_queries_reference_stage_search_corpus_documents(self) -> None:
        corpus_documents = set(list_s4_search_corpus_documents())
        for query in load_s4_hybrid_search_queries():
            if query.expect_doc is None:
                continue
            assert query.expect_doc in corpus_documents

    def test_synonym_queries_align_with_lexicon_owner(self) -> None:
        lexicon = build_stage_query_lexicon_index()
        synonym_lexicon_ids: set[str] = set()
        for query in load_s4_hybrid_search_queries():
            if query.query_type != "synonym":
                continue
            assert query.lexicon_id is not None
            assert query.expect_doc is not None
            assert lexicon[query.lexicon_id].trigger_query == query.query
            synonym_lexicon_ids.add(query.lexicon_id)
        assert synonym_lexicon_ids == set(lexicon)
        assert len(synonym_lexicon_ids) == S4_EXPECTED_SYNONYM_QUERY_COUNT

"""End-to-end hybrid search integration tests + S4 stage golden Top10 verification."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from opendocs.app.search_service import SearchService
from opendocs.indexing.hnsw_manager import HnswManager
from opendocs.retrieval.embedder import LocalNgramEmbedder
from opendocs.retrieval.query_lexicon import build_stage_query_lexicon_index
from opendocs.retrieval.stage_golden_queries import (
    S4_EXPECTED_SYNONYM_QUERY_COUNT,
    load_s4_hybrid_search_queries,
)
from opendocs.storage.db import session_scope
from opendocs.utils.logging import init_logging


class TestHybridSearch:
    """Core search functionality tests."""

    def test_long_cjk_fts_plus_dense(self, search_service: SearchService) -> None:
        """4-char Chinese query should hit via both FTS trigram and dense."""
        resp = search_service.search("项目进度")
        assert len(resp.results) > 0
        paths = [r.citation.path for r in resp.results]
        assert any("zh_project_plan" in p for p in paths)

    def test_short_cjk_dense_only(self, search_service: SearchService) -> None:
        """2-char Chinese query — FTS returns empty, dense should compensate."""
        resp = search_service.search("项目")
        assert len(resp.results) > 0
        paths = [r.citation.path for r in resp.results]
        assert any("zh_project_plan" in p for p in paths)

    def test_short_en_dense_only(self, search_service: SearchService) -> None:
        """2-char English query — FTS returns empty, dense should compensate."""
        resp = search_service.search("AI")
        assert len(resp.results) > 0
        paths = [r.citation.path for r in resp.results]
        assert any("mixed_tech_report" in p for p in paths)

    def test_fullwidth_short_en_dense_only(self, search_service: SearchService) -> None:
        """Fullwidth short English query must normalize onto the same dense path."""
        resp = search_service.search("ＡＩ")
        assert len(resp.results) > 0
        paths = [r.citation.path for r in resp.results]
        assert any("mixed_tech_report" in p for p in paths)

    def test_english_both_channels(self, search_service: SearchService) -> None:
        """Long English query should hit via both channels."""
        resp = search_service.search("authentication")
        assert len(resp.results) > 0
        paths = [r.citation.path for r in resp.results]
        assert any("en_weekly_report" in p for p in paths)

    def test_mixed_language_query(self, search_service: SearchService) -> None:
        resp = search_service.search("machine learning")
        assert len(resp.results) > 0
        paths = [r.citation.path for r in resp.results]
        assert any("mixed_tech_report" in p for p in paths)

    def test_stage_synonym_queries_hit_expected_documents(
        self,
        search_service: SearchService,
    ) -> None:
        match_queries, _ = _load_stage_golden_queries()
        synonym_queries = [
            (query, expect_doc)
            for query_type, query, expect_doc, _ in match_queries
            if query_type == "synonym"
        ]

        assert len(synonym_queries) == S4_EXPECTED_SYNONYM_QUERY_COUNT
        assert len(synonym_queries) == len(build_stage_query_lexicon_index())
        for query, expect_doc in synonym_queries:
            resp = search_service.search(query, top_k=10)
            paths = [result.citation.path for result in resp.results]
            assert any(expect_doc in path for path in paths), query

    def test_zero_result(self, search_service: SearchService) -> None:
        """Nonsensical query with unique n-grams should produce very few or no results."""
        resp = search_service.search("qxzjkw vbnmrt ypflg")
        # With unique n-grams, either empty or extremely low scores
        if resp.results:
            # Any results should have very low hybrid scores
            assert resp.results[0].score < 0.30

    def test_empty_query_raises(self, search_service: SearchService) -> None:
        with pytest.raises(ValueError):
            search_service.search("")

    @pytest.mark.parametrize(
        ("query", "expect_path_fragment"),
        [("项目", "zh_project_plan"), ("AI", "mixed_tech_report")],
    )
    def test_startup_repairs_legacy_hnsw_without_dirty_flag(
        self,
        indexed_search_env,
        query: str,
        expect_path_fragment: str,
    ) -> None:
        """Legacy 64-dim HNSW files must be repaired before the first dense-only query."""
        engine, _, hnsw_path = indexed_search_env

        legacy_hnsw = HnswManager(hnsw_path, dim=64)
        legacy_hnsw.rebuild_from_db(engine)
        assert legacy_hnsw.is_dirty() is False

        service = SearchService(engine, hnsw_path=hnsw_path)
        resp = service.search(query)

        assert len(resp.results) > 0
        assert any(expect_path_fragment in r.citation.path for r in resp.results)
        assert any(r.score_breakdown.dense_normalized > 0 for r in resp.results)

    def test_startup_repairs_same_dim_signature_mismatch(
        self,
        indexed_search_env,
    ) -> None:
        """Signature drift must rebuild even when HNSW dim has not changed."""
        engine, _, hnsw_path = indexed_search_env

        with session_scope(engine) as session:
            session.execute(
                text(
                    "UPDATE index_artifacts "
                    "SET status = 'ready', embedder_signature = :sig "
                    "WHERE artifact_name = 'dense_hnsw'"
                ),
                {"sig": "legacy-same-dim-signature"},
            )

        service = SearchService(engine, hnsw_path=hnsw_path)
        resp = service.search("AI")

        assert len(resp.results) > 0
        assert any("mixed_tech_report" in r.citation.path for r in resp.results)
        with session_scope(engine) as session:
            row = session.execute(
                text(
                    "SELECT status, embedder_signature, last_reason "
                    "FROM index_artifacts WHERE artifact_name = 'dense_hnsw'"
                )
            ).one()
        assert row[0] == "ready"
        assert row[1] == LocalNgramEmbedder().fingerprint
        assert row[2] == "embedder_signature_changed"


class TestSearchResultStructure:
    """Verify result structure matches §8.4 citation requirements."""

    def test_result_has_citation_fields(self, search_service: SearchService) -> None:
        resp = search_service.search("项目进度")
        assert len(resp.results) > 0
        result = resp.results[0]
        assert result.title
        assert result.path
        assert not Path(result.path).is_absolute()
        assert result.path == result.citation.path
        assert not hasattr(result, "absolute_path")
        assert result.summary
        assert result.citation.doc_id
        assert result.citation.chunk_id
        assert result.citation.char_range
        assert result.citation.quote_preview

    def test_score_breakdown_present(self, search_service: SearchService) -> None:
        resp = search_service.search("项目进度")
        assert len(resp.results) > 0
        bd = resp.results[0].score_breakdown
        assert hasattr(bd, "lexical_normalized")
        assert hasattr(bd, "dense_normalized")
        assert hasattr(bd, "freshness_boost")
        assert hasattr(bd, "hybrid_score")

    def test_results_sorted_by_score(self, search_service: SearchService) -> None:
        resp = search_service.search("项目进度")
        scores = [r.score for r in resp.results]
        assert scores == sorted(scores, reverse=True)

    def test_search_audit_never_persists_raw_query(
        self,
        indexed_search_env,
        tmp_path: Path,
    ) -> None:
        engine, _, hnsw_path = indexed_search_env
        init_logging(tmp_path / "logs")
        service = SearchService(engine, hnsw_path=hnsw_path)

        service.search("password=abc123 token=mytoken secret=hide-me")

        audit_log = tmp_path / "logs" / "audit.jsonl"
        content = audit_log.read_text(encoding="utf-8")
        assert "password=abc123" not in content
        assert "mytoken" not in content
        assert "hide-me" not in content
        assert "query_sha256" in content


def _load_stage_golden_queries() -> tuple[list[tuple[str, str, str, str | None]], list[str]]:
    """Load queries from the stage-owned S4 golden hybrid search asset.

    Returns (match_queries, zero_queries) where match_queries is
    list of (query_type, query, expect_doc, lexicon_id) and zero_queries is list of query strings.
    """
    match_queries: list[tuple[str, str, str, str | None]] = []
    zero_queries: list[str] = []
    for golden_query in load_s4_hybrid_search_queries():
        if golden_query.query_type == "zero":
            zero_queries.append(golden_query.query)
            continue
        assert golden_query.expect_doc is not None
        match_queries.append(
            (
                golden_query.query_type,
                golden_query.query,
                golden_query.expect_doc,
                golden_query.lexicon_id,
            )
        )
    return match_queries, zero_queries


class TestRegressionTop10:
    """Run the S4 stage golden query set and verify >= 90% Top10 hit rate."""

    def test_regression_top10_hit_rate(self, search_service: SearchService) -> None:
        match_queries, zero_queries = _load_stage_golden_queries()
        assert len(match_queries) > 0, "No stage golden queries loaded from JSON"
        assert sum(1 for query_type, _, _, _ in match_queries if query_type == "locating") == 5
        assert sum(1 for query_type, _, _, _ in match_queries if query_type == "synonym") == (
            len(build_stage_query_lexicon_index())
        )

        hits = 0
        total = 0

        for _, query, expect_doc, _ in match_queries:
            resp = search_service.search(query, top_k=10)
            paths = [r.citation.path for r in resp.results]
            found = any(expect_doc in p for p in paths)
            if found:
                hits += 1
            total += 1

        for query in zero_queries:
            resp = search_service.search(query)
            is_zero = len(resp.results) == 0 or resp.results[0].score < 0.30
            if is_zero:
                hits += 1
            total += 1

        hit_rate = hits / total if total else 0.0
        assert hit_rate >= 0.9, f"Top10 hit rate {hit_rate:.0%} ({hits}/{total}) < 90%"

"""Integration tests for search filter combinations."""

from __future__ import annotations

from sqlalchemy import text

from opendocs.app.search_service import SearchService
from opendocs.retrieval.filters import SearchFilter
from opendocs.retrieval.stage_filter_cases import load_s4_search_filter_cases
from opendocs.storage.db import session_scope


class TestFilterCombinations:
    def test_stage_filter_cases(self, indexed_search_env, search_corpus) -> None:
        engine, _, hnsw_path = indexed_search_env
        service = SearchService(engine, hnsw_path=hnsw_path)

        with session_scope(engine) as session:
            source_root_id = session.execute(text("SELECT source_root_id FROM documents LIMIT 1")).scalar_one()

        for filter_case in load_s4_search_filter_cases():
            resp = service.search(
                filter_case.query,
                filters=filter_case.build_filter(
                    corpus_dir=search_corpus,
                    primary_source_root_id=source_root_id,
                ),
            )
            assert len(resp.results) > 0, filter_case.case_id
            assert all(filter_case.expect_doc in result.path for result in resp.results), filter_case.case_id

    def test_filter_by_file_type_md(self, search_service: SearchService) -> None:
        resp = search_service.search(
            "项目进度",
            filters=SearchFilter(file_types=["md"]),
        )
        for r in resp.results:
            assert r.path.endswith(".md")

    def test_filter_by_file_type_txt(self, search_service: SearchService) -> None:
        resp = search_service.search(
            "authentication",
            filters=SearchFilter(file_types=["txt"]),
        )
        for r in resp.results:
            assert r.path.endswith(".txt")

    def test_filter_no_match_returns_empty(self, search_service: SearchService) -> None:
        resp = search_service.search(
            "项目进度",
            filters=SearchFilter(file_types=["pdf"]),
        )
        assert len(resp.results) == 0

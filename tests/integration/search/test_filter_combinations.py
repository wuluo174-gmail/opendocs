"""Integration tests for search filter combinations."""

from __future__ import annotations

from pathlib import Path

from opendocs.app.index_service import IndexService
from opendocs.app.search_service import SearchService
from opendocs.app.source_service import SourceService
from opendocs.retrieval.filters import SearchFilter
from opendocs.retrieval.stage_filter_cases import load_s4_search_filter_cases
from opendocs.storage.db import build_sqlite_engine, init_db


class TestFilterCombinations:
    def test_stage_filter_cases(self, indexed_search_env, search_corpus) -> None:
        engine, _, hnsw_path = indexed_search_env
        service = SearchService(engine, hnsw_path=hnsw_path)

        for filter_case in load_s4_search_filter_cases():
            resp = service.search(
                filter_case.query,
                filters=filter_case.build_filter(corpus_dir=search_corpus),
            )
            assert len(resp.results) > 0, filter_case.case_id
            assert all(filter_case.expect_doc in result.path for result in resp.results), (
                filter_case.case_id
            )

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

    def test_filter_by_display_root_label(self, search_service: SearchService) -> None:
        resp = search_service.search(
            "项目",
            filters=SearchFilter(source_roots=["corpus"]),
        )
        assert len(resp.results) > 0
        assert all(result.path.startswith("corpus/") for result in resp.results)

    def test_root_and_directory_filters_use_and_semantics(self, tmp_path: Path) -> None:
        root_a = _write_multi_root_doc(tmp_path / "root_a", filename="alpha_a.md")
        _write_multi_root_doc(tmp_path / "root_b", filename="alpha_b.md")

        db_path = tmp_path / "multi_root.db"
        init_db(db_path)
        engine = build_sqlite_engine(db_path)
        hnsw_path = tmp_path / "hnsw" / "multi_root.hnsw"
        hnsw_path.parent.mkdir(parents=True, exist_ok=True)

        source_service = SourceService(engine)
        source_a = source_service.add_source(root_a)
        source_b = source_service.add_source(tmp_path / "root_b")
        index_service = IndexService(engine, hnsw_path=hnsw_path)
        index_service.full_index_source(source_a.source_root_id)
        index_service.full_index_source(source_b.source_root_id)
        service = SearchService(engine, hnsw_path=hnsw_path)

        resp = service.search(
            "shared-needle",
            filters=SearchFilter(
                source_roots=[str(root_a.resolve())],
                directory_prefixes=["projects/alpha"],
            ),
        )

        assert len(resp.results) > 0
        assert all(result.path.startswith("root_a/") for result in resp.results)


def _write_multi_root_doc(root: Path, *, filename: str) -> Path:
    directory = root / "projects" / "alpha"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(
        "# Shared\n\nshared-needle retrieval target",
        encoding="utf-8",
    )
    return root

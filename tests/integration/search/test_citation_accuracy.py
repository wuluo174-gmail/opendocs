"""Integration tests for citation accuracy (backend contract, not TC-018 UI)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from opendocs.app.runtime import OpenDocsRuntime
from opendocs.app.search_service import SearchService
from opendocs.app.source_service import SourceService
from opendocs.storage.db import build_sqlite_engine, init_db, session_scope


class TestCitationAccuracy:
    def test_citation_path_is_source_relative(self, search_service: SearchService) -> None:
        """Citation path should use the source-relative display path."""
        resp = search_service.search("项目进度")
        assert len(resp.results) > 0
        for r in resp.results:
            assert not Path(r.citation.path).is_absolute()
            assert r.citation.path == r.path

    def test_citation_char_range_valid(self, search_service: SearchService) -> None:
        resp = search_service.search("authentication")
        assert len(resp.results) > 0
        for r in resp.results:
            parts = r.citation.char_range.split("-")
            assert len(parts) == 2
            start, end = int(parts[0]), int(parts[1])
            assert start >= 0
            assert end >= start

    def test_citation_quote_preview_nonempty(self, search_service: SearchService) -> None:
        resp = search_service.search("会议纪要")
        assert len(resp.results) > 0
        for r in resp.results:
            assert len(r.citation.quote_preview) > 0

    def test_locate_evidence(self, search_service: SearchService) -> None:
        """SearchService.locate_evidence should return location data."""
        resp = search_service.search("项目进度")
        assert len(resp.results) > 0
        r = resp.results[0]
        loc = search_service.locate_evidence(r.doc_id, r.chunk_id)
        assert loc is not None
        assert not Path(loc.path).is_absolute()
        assert loc.path == r.path
        assert loc.quote_preview
        if loc.paragraph_range is not None:
            assert all(int(part) >= 1 for part in loc.paragraph_range.split("-"))

    def test_load_evidence_preview_returns_located_excerpt(
        self,
        search_service: SearchService,
    ) -> None:
        resp = search_service.search("项目进度")
        assert len(resp.results) > 0
        r = resp.results[0]

        preview = search_service.load_evidence_preview(r.doc_id, r.chunk_id)
        assert preview is not None
        assert not Path(preview.path).is_absolute()
        assert preview.path == r.path
        assert preview.preview_text
        assert preview.highlight_end > preview.highlight_start
        normalized_quote = " ".join(r.citation.quote_preview.replace("...", "").split())
        normalized_preview = " ".join(preview.preview_text.split())
        assert normalized_quote in normalized_preview

    def test_citation_path_disambiguates_same_relative_path_across_source_roots(
        self,
        tmp_path: Path,
    ) -> None:
        db_path = tmp_path / "multi-root.db"
        hnsw_path = tmp_path / "hnsw" / "multi-root.hnsw"
        hnsw_path.parent.mkdir(parents=True, exist_ok=True)

        source_root_a = tmp_path / "workspace-a" / "shared-root"
        source_root_b = tmp_path / "workspace-b" / "shared-root"
        source_root_a.mkdir(parents=True)
        source_root_b.mkdir(parents=True)
        (source_root_a / "report.md").write_text(
            "# Report\n\nshared needle alpha",
            encoding="utf-8",
        )
        (source_root_b / "report.md").write_text("# Report\n\nshared needle beta", encoding="utf-8")

        init_db(db_path)
        engine = build_sqlite_engine(db_path)
        runtime = OpenDocsRuntime(engine, hnsw_path=hnsw_path)
        source_service = SourceService(engine, runtime=runtime)
        index_service = runtime.build_index_service()

        try:
            source_a = source_service.add_source(source_root_a)
            source_b = source_service.add_source(source_root_b)
            index_service.full_index_source(source_a.source_root_id)
            index_service.full_index_source(source_b.source_root_id)

            service = runtime.build_search_service()
            resp = service.search("shared needle", top_k=10)
        finally:
            runtime.close()

        report_paths = [result.path for result in resp.results if result.title == "Report"]
        assert len(report_paths) >= 2
        assert len(set(report_paths)) == len(report_paths)
        assert all(not Path(path).is_absolute() for path in report_paths)
        assert all(path.endswith("/report.md") for path in report_paths[:2])

    def test_locate_evidence_rejects_mismatched_doc_and_chunk(self, indexed_search_env) -> None:
        """EvidenceLocation must not stitch fields from two different documents."""
        engine, _, hnsw_path = indexed_search_env
        with OpenDocsRuntime(engine, hnsw_path=hnsw_path) as runtime:
            service = runtime.build_search_service()

            with session_scope(engine) as session:
                rows = session.execute(
                    text(
                        "SELECT d.doc_id, c.chunk_id "
                        "FROM documents d "
                        "JOIN chunks c ON d.doc_id = c.doc_id "
                        "ORDER BY d.path, c.chunk_index"
                    )
                ).fetchall()

            assert len(rows) >= 2
            loc = service.locate_evidence(rows[0][0], rows[-1][1])
            assert loc is None

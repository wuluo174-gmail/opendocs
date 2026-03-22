"""Integration tests for citation accuracy (backend contract, not TC-018 UI)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from opendocs.app.search_service import SearchService
from opendocs.storage.db import session_scope


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

    def test_locate_evidence_rejects_mismatched_doc_and_chunk(self, indexed_search_env) -> None:
        """EvidenceLocation must not stitch fields from two different documents."""
        engine, _, hnsw_path = indexed_search_env
        service = SearchService(engine, hnsw_path=hnsw_path)

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

"""Unit tests for SearchPipeline — structure + mock-based orchestration."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from unittest.mock import MagicMock, patch

from opendocs.retrieval.evidence import SearchResponse
from opendocs.retrieval.query_preprocessor import PreparedQuery, QueryVariant
from opendocs.retrieval.search_pipeline import SearchPipeline
from opendocs.storage.repositories.chunk_repository import SearchChunkRecord


class TestSearchPipelineStructure:
    def test_pipeline_has_execute(self) -> None:
        assert hasattr(SearchPipeline, "execute")

    def test_search_response_fields(self) -> None:
        field_names = {f.name for f in fields(SearchResponse)}
        assert "query" in field_names
        assert "results" in field_names
        assert "total_candidates" in field_names
        assert "trace_id" in field_names
        assert "duration_sec" in field_names
        assert "filters_applied" in field_names


class TestSearchPipelineOrchestration:
    def test_empty_fts_and_dense_returns_empty(self) -> None:
        """When both channels return empty, pipeline returns empty response."""
        engine = MagicMock()
        hnsw = MagicMock()
        hnsw.query.return_value = []
        embedder = MagicMock()
        embedder.embed_text.return_value = MagicMock()

        pipeline = SearchPipeline(engine, hnsw, embedder)

        with patch.object(pipeline._fts, "search_prepared", return_value=[]):
            with patch("opendocs.retrieval.search_pipeline.session_scope") as mock_scope:
                mock_session = MagicMock()
                mock_scope.return_value.__enter__ = MagicMock(return_value=mock_session)
                mock_scope.return_value.__exit__ = MagicMock(return_value=False)

                with patch(
                    "opendocs.retrieval.search_pipeline.apply_pre_filter",
                    return_value=None,
                ):
                    resp = pipeline.execute("test query")

        assert isinstance(resp, SearchResponse)
        assert resp.query == "test query"
        assert resp.results == []

    def test_both_channels_invoked(self) -> None:
        """Verify both FTS and dense channels are called (mandatory hybrid)."""
        engine = MagicMock()
        hnsw = MagicMock()
        hnsw.query.return_value = []
        embedder = MagicMock()
        embedder.embed_text.return_value = MagicMock()

        pipeline = SearchPipeline(engine, hnsw, embedder)

        fts_mock = MagicMock(return_value=[])
        dense_mock = MagicMock(return_value=[])

        with patch.object(pipeline._fts, "search_prepared", fts_mock):
            with patch.object(pipeline._dense, "search", dense_mock):
                with patch("opendocs.retrieval.search_pipeline.session_scope") as mock_scope:
                    mock_session = MagicMock()
                    mock_scope.return_value.__enter__ = MagicMock(return_value=mock_session)
                    mock_scope.return_value.__exit__ = MagicMock(return_value=False)

                    with patch(
                        "opendocs.retrieval.search_pipeline.apply_pre_filter",
                        return_value=None,
                    ):
                        pipeline.execute("test query")

        fts_mock.assert_called_once()
        dense_mock.assert_called_once()

    def test_pipeline_uses_single_normalized_query_for_fts_and_dense(self) -> None:
        engine = MagicMock()
        hnsw = MagicMock()
        embedder = MagicMock()
        pipeline = SearchPipeline(engine, hnsw, embedder)
        prepared = PreparedQuery(variants=(QueryVariant(text="AI", fts_query="AI"),))

        with patch.object(pipeline._preprocessor, "prepare", return_value=prepared) as prepare_mock:
            with patch.object(pipeline._fts, "search_prepared", return_value=[]) as fts_mock:
                with patch.object(pipeline._dense, "search", return_value=[]) as dense_mock:
                    with patch("opendocs.retrieval.search_pipeline.session_scope") as mock_scope:
                        mock_session = MagicMock()
                        mock_scope.return_value.__enter__ = MagicMock(return_value=mock_session)
                        mock_scope.return_value.__exit__ = MagicMock(return_value=False)

                        with patch(
                            "opendocs.retrieval.search_pipeline.apply_pre_filter",
                            return_value=None,
                        ):
                            pipeline.execute("ＡＩ", top_k=2)

        prepare_mock.assert_called_once_with("ＡＩ")
        fts_mock.assert_called_once_with(
            mock_session,
            prepared,
            doc_ids=None,
            limit=6,
        )
        dense_mock.assert_called_once_with("AI", k=6)

    def test_pipeline_searches_all_query_variants_in_dense_channel(self) -> None:
        engine = MagicMock()
        hnsw = MagicMock()
        embedder = MagicMock()
        pipeline = SearchPipeline(engine, hnsw, embedder)
        prepared = PreparedQuery(
            variants=(
                QueryVariant(text="roadmap", fts_query="roadmap"),
                QueryVariant(text="Project Plan", fts_query="Project Plan"),
            )
        )

        with patch.object(pipeline._preprocessor, "prepare", return_value=prepared):
            with patch.object(pipeline._fts, "search_prepared", return_value=[]):
                with patch.object(pipeline._dense, "search", return_value=[]) as dense_mock:
                    with patch("opendocs.retrieval.search_pipeline.session_scope") as mock_scope:
                        mock_session = MagicMock()
                        mock_scope.return_value.__enter__ = MagicMock(return_value=mock_session)
                        mock_scope.return_value.__exit__ = MagicMock(return_value=False)

                        with patch(
                            "opendocs.retrieval.search_pipeline.apply_pre_filter",
                            return_value=None,
                        ):
                            pipeline.execute("roadmap", top_k=2)

        assert dense_mock.call_count == 2
        dense_mock.assert_any_call("roadmap", k=6)
        dense_mock.assert_any_call("Project Plan", k=6)

    def test_pipeline_uses_exact_dense_subset_when_filters_are_active(self) -> None:
        engine = MagicMock()
        hnsw = MagicMock()
        embedder = MagicMock()
        pipeline = SearchPipeline(engine, hnsw, embedder)
        prepared = PreparedQuery(variants=(QueryVariant(text="AI", fts_query="AI"),))

        with patch.object(pipeline._preprocessor, "prepare", return_value=prepared):
            with patch.object(pipeline._fts, "search_prepared", return_value=[]):
                with patch.object(pipeline._dense, "search", return_value=[]) as dense_mock:
                    with patch.object(
                        pipeline._dense,
                        "search_filtered",
                        return_value=[],
                    ) as filtered_mock:
                        with patch(
                            "opendocs.retrieval.search_pipeline.session_scope"
                        ) as mock_scope:
                            mock_session = MagicMock()
                            mock_scope.return_value.__enter__ = MagicMock(return_value=mock_session)
                            mock_scope.return_value.__exit__ = MagicMock(return_value=False)

                            with (
                                patch(
                                    "opendocs.retrieval.search_pipeline.apply_pre_filter",
                                    return_value={"doc-1"},
                                ),
                                patch(
                                    "opendocs.retrieval.search_pipeline.ChunkRepository.list_chunk_ids_by_doc_ids",
                                    return_value={"chunk-1", "chunk-2"},
                                ),
                                patch(
                                    "opendocs.retrieval.search_pipeline.ChunkRepository.load_search_records",
                                    return_value={},
                                ),
                            ):
                                pipeline.execute("AI", top_k=2)

        dense_mock.assert_not_called()
        filtered_mock.assert_called_once_with(
            "AI",
            allowed_ids={"chunk-1", "chunk-2"},
            k=6,
        )

    def test_pipeline_builds_results_from_batch_loaded_search_records(self) -> None:
        engine = MagicMock()
        hnsw = MagicMock()
        embedder = MagicMock()
        pipeline = SearchPipeline(engine, hnsw, embedder)
        prepared = PreparedQuery(variants=(QueryVariant(text="AI", fts_query="AI"),))
        record = SearchChunkRecord(
            chunk_id="chunk-1",
            doc_id="doc-1",
            text="batch loaded retrieval evidence",
            char_start=5,
            char_end=34,
            page_no=None,
            paragraph_start=0,
            paragraph_end=0,
            heading_path="Overview",
            title="Batch Result",
            display_path="workspace/report.md",
            modified_at=datetime(2026, 3, 1, 12, 0, 0),
        )

        with patch.object(pipeline._preprocessor, "prepare", return_value=prepared):
            with patch.object(
                pipeline._fts,
                "search_prepared",
                return_value=[("chunk-1", "doc-1", -2.0)],
            ):
                with patch.object(
                    pipeline._dense,
                    "search",
                    return_value=[("chunk-1", 0.2)],
                ):
                    with patch("opendocs.retrieval.search_pipeline.session_scope") as mock_scope:
                        mock_session = MagicMock()
                        mock_scope.return_value.__enter__ = MagicMock(return_value=mock_session)
                        mock_scope.return_value.__exit__ = MagicMock(return_value=False)

                        with (
                            patch(
                                "opendocs.retrieval.search_pipeline.apply_pre_filter",
                                return_value=None,
                            ),
                            patch(
                                "opendocs.retrieval.search_pipeline.ChunkRepository.load_search_records",
                                return_value={"chunk-1": record},
                            ),
                            patch(
                                "opendocs.retrieval.search_pipeline.ChunkRepository.get_by_id",
                                side_effect=AssertionError("must not load chunks one-by-one"),
                            ),
                        ):
                            resp = pipeline.execute("AI", top_k=2)

        assert len(resp.results) == 1
        result = resp.results[0]
        assert result.chunk_id == "chunk-1"
        assert result.doc_id == "doc-1"
        assert result.title == "Batch Result"
        assert result.path == "workspace/report.md"
        assert result.citation.char_range == "5-34"
        assert resp.total_candidates == 1

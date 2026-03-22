"""S3-T04: Rebuild idempotency and failure recovery tests."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from opendocs.app.index_service import IndexService
from opendocs.app.source_service import SourceService
from opendocs.domain.models import SourceRootModel
from opendocs.indexing.chunker import Chunker
from opendocs.indexing.hnsw_manager import HnswManager
from opendocs.indexing.index_builder import IndexBuilder
from opendocs.indexing.scanner import Scanner
from opendocs.parsers import create_default_registry
from opendocs.retrieval.embedder import LocalNgramEmbedder
from opendocs.storage.db import session_scope
from opendocs.utils.time import utcnow_naive


class TestRebuildIdempotent:
    """Rebuild twice produces identical state; failures don't corrupt."""

    def test_rebuild_twice_same_result(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)

        r1 = index_service.rebuild_index(source.source_root_id)
        with session_scope(engine) as session:
            doc_count_1 = session.execute(text("SELECT COUNT(*) FROM documents")).scalar()
            chunk_count_1 = session.execute(text("SELECT COUNT(*) FROM chunks")).scalar()

        r2 = index_service.rebuild_index(source.source_root_id)
        with session_scope(engine) as session:
            doc_count_2 = session.execute(text("SELECT COUNT(*) FROM documents")).scalar()
            chunk_count_2 = session.execute(text("SELECT COUNT(*) FROM chunks")).scalar()

        assert doc_count_1 == doc_count_2
        assert chunk_count_1 == chunk_count_2
        # Both runs should have same success/failure counts
        assert r1.success_count == r2.success_count
        assert r1.failed_count == r2.failed_count

    def test_rebuild_creates_scan_run(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        """S3-T01: manual rebuild scans should also persist scan_run records."""
        source = source_service.add_source(corpus_copy)

        with session_scope(engine) as session:
            before = session.execute(text("SELECT COUNT(*) FROM scan_runs")).scalar()

        index_service.rebuild_index(source.source_root_id)

        with session_scope(engine) as session:
            after = session.execute(text("SELECT COUNT(*) FROM scan_runs")).scalar()
            latest = session.execute(
                text(
                    "SELECT source_root_id, status, trace_id "
                    "FROM scan_runs ORDER BY started_at DESC LIMIT 1"
                )
            ).one()

        assert after == before + 1
        assert latest[0] == source.source_root_id
        assert latest[1] == "completed"
        assert latest[2]

    def test_rebuild_audit_targets_scan_run(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        """S3-T01: rebuild batch audit should point to the concrete scan_run, not source config."""
        source = source_service.add_source(corpus_copy)
        index_service.rebuild_index(source.source_root_id)

        with session_scope(engine) as session:
            audit = session.execute(
                text(
                    "SELECT target_id, trace_id, detail_json "
                    "FROM audit_logs WHERE operation = 'index_rebuild' "
                    "ORDER BY timestamp DESC LIMIT 1"
                )
            ).one()
            linked_scan_run = session.execute(
                text(
                    "SELECT scan_run_id, trace_id FROM scan_runs WHERE scan_run_id = :scan_run_id"
                ),
                {"scan_run_id": audit[0]},
            ).one()
            detail = json.loads(audit[2])

        assert audit[0] == linked_scan_run[0]
        assert audit[1] == linked_scan_run[1]
        assert detail["source_root_id"] == source.source_root_id
        assert detail["scan_run_id"] == linked_scan_run[0]

    def test_rebuild_no_dirty_duplicates(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        """Rebuild must not create duplicate documents or chunks."""
        source = source_service.add_source(corpus_copy)
        index_service.rebuild_index(source.source_root_id)
        index_service.rebuild_index(source.source_root_id)

        with session_scope(engine) as session:
            # Each path should appear exactly once
            dup_paths = session.execute(
                text("SELECT path, COUNT(*) as cnt FROM documents GROUP BY path HAVING cnt > 1")
            ).fetchall()
            assert len(dup_paths) == 0

            # Each (doc_id, chunk_index) should be unique
            dup_chunks = session.execute(
                text(
                    "SELECT doc_id, chunk_index, COUNT(*) as cnt "
                    "FROM chunks GROUP BY doc_id, chunk_index HAVING cnt > 1"
                )
            ).fetchall()
            assert len(dup_chunks) == 0

    def test_rebuild_hnsw_synced(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        result = index_service.rebuild_index(source.source_root_id)
        assert result.hnsw_status == "synced"
        with session_scope(engine) as session:
            row = session.execute(
                text(
                    "SELECT status, embedder_model, embedder_signature "
                    "FROM index_artifacts WHERE artifact_name = 'dense_hnsw'"
                )
            ).one()
        assert row[0] == "ready"
        assert row[1] == LocalNgramEmbedder.MODEL_NAME
        assert row[2] == LocalNgramEmbedder().fingerprint

    def test_modified_file_updated_on_rebuild(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        """Modified file content is updated after rebuild (force=True)."""
        source = source_service.add_source(corpus_copy)
        index_service.rebuild_index(source.source_root_id)

        # Modify a file
        target = corpus_copy / "report_001.txt"
        target.write_text("MODIFIED CONTENT UNIQUE_KW_REBUILD_MOD")

        index_service.rebuild_index(source.source_root_id)

        with session_scope(engine) as session:
            rows = session.execute(
                text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'UNIQUE_KW_REBUILD_MOD'")
            ).fetchall()
            assert len(rows) >= 1

            # Old content should be gone
            old_rows = session.execute(
                text("SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'UNIQUE_KW_001'")
            ).fetchall()
            assert len(old_rows) == 0

    def test_failed_file_retried_on_rebuild(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        """FR-002/S3-T04: rebuild retries previously failed files (force=True)."""
        source = source_service.add_source(corpus_copy)

        # First full index: corrupted.pdf will fail
        r1 = index_service.full_index_source(source.source_root_id)
        failed_paths = [r.path for r in r1.results if r.status == "failed"]
        corrupted = [p for p in failed_paths if "corrupted" in p]
        assert len(corrupted) >= 1, "corrupted.pdf should fail on first index"

        # Rebuild with force=True: corrupted.pdf must be re-processed (not skipped)
        r2 = index_service.rebuild_index(source.source_root_id)
        corrupted_results = [r for r in r2.results if "corrupted" in r.path]
        assert len(corrupted_results) == 1
        # It will still fail (file is actually corrupt), but it was RETRIED not SKIPPED
        assert corrupted_results[0].status == "failed"
        assert corrupted_results[0].status != "skipped"

    def test_batch_hnsw_compensation_rebuilds_with_embedder(
        self,
        engine: Engine,
        hnsw_path: Path,
        corpus_copy: Path,
        monkeypatch,
    ) -> None:
        """Dirty compensation must rebuild with real embeddings, not zero vectors."""
        registry = create_default_registry()
        scanner = Scanner(registry)
        embedder = LocalNgramEmbedder()
        hnsw = HnswManager(hnsw_path, dim=embedder.dim)
        builder = IndexBuilder(
            engine,
            registry,
            Chunker(),
            hnsw_manager=hnsw,
            embedder=embedder,
        )

        source_root_id = str(uuid.uuid4())
        with session_scope(engine) as session:
            session.add(
                SourceRootModel(
                    source_root_id=source_root_id,
                    path=str(corpus_copy),
                    label="rebuild fixture",
                    exclude_rules_json={},
                    recursive=True,
                    is_active=True,
                    created_at=utcnow_naive(),
                    updated_at=utcnow_naive(),
                )
            )

        scan = scanner.scan(corpus_copy, source_root_id=source_root_id)
        trace = {"add_calls": 0, "rebuild_embedder": None}

        original_add = hnsw.add_chunks_with_vectors
        original_rebuild = hnsw.rebuild_from_db

        def flaky_add(chunk_ids: list[str], vectors) -> None:
            trace["add_calls"] += 1
            if trace["add_calls"] == 1:
                raise RuntimeError("simulated hnsw add failure")
            original_add(chunk_ids, vectors)

        def capture_rebuild(engine_arg: Engine, embedder=None, reason=None) -> None:
            trace["rebuild_embedder"] = embedder
            trace["rebuild_reason"] = reason
            original_rebuild(engine_arg, embedder=embedder, reason=reason)

        monkeypatch.setattr(hnsw, "add_chunks_with_vectors", flaky_add)
        monkeypatch.setattr(hnsw, "rebuild_from_db", capture_rebuild)

        result = builder.index_batch(
            scan.included,
            source_root_id=source_root_id,
            trace_id=str(uuid.uuid4()),
        )

        assert result.hnsw_status == "synced"
        assert trace["rebuild_embedder"] is embedder
        assert hnsw.is_dirty() is False
        with session_scope(engine) as session:
            row = session.execute(
                text(
                    "SELECT status, embedder_signature, last_reason "
                    "FROM index_artifacts WHERE artifact_name = 'dense_hnsw'"
                )
            ).one()
        assert row[0] == "ready"
        assert row[1] == embedder.fingerprint
        assert row[2] == "batch_compensation_dirty"

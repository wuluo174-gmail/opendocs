"""S3 service-boundary regressions for scan runs and semantic artifact visibility."""

from __future__ import annotations

import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from opendocs.app.index_service import IndexService
from opendocs.app.runtime import OpenDocsRuntime
from opendocs.app.search_service import SearchService
from opendocs.app.source_service import SourceService
from opendocs.exceptions import RuntimeClosedError, RuntimeOwnershipError
from opendocs.indexing.semantic_indexer import SemanticIndexer
from opendocs.retrieval.embedder import LocalSemanticEmbedder
from opendocs.runtime_paths import resolve_runtime_hnsw_path, resolve_runtime_root_from_db_path
from opendocs.storage.db import build_sqlite_engine, session_scope
from opendocs.storage.repositories import IndexArtifactRepository
from opendocs.utils.time import utcnow_naive


def _count_generation_gc_workers() -> int:
    return sum(
        1
        for thread in threading.enumerate()
        if thread.name == "OpenDocsGenerationLifecycleWorker" and thread.is_alive()
    )


class TestS3SemanticVisibility:
    """Keep S3 visibility contracts inside S3 instead of leaking into later stages."""

    def test_source_service_lists_scan_runs_latest_first(
        self,
        source_service: SourceService,
        index_service: IndexService,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.full_index_source(source.source_root_id)

        changed = corpus_copy / "scan_run_visibility_note.md"
        changed.write_text("Scan run visibility regression note.", encoding="utf-8")
        index_service.update_index_for_changes(source.source_root_id)

        runs = source_service.list_scan_runs(source.source_root_id)

        assert len(runs) >= 2
        assert all(run.source_root_id == source.source_root_id for run in runs)
        assert runs[0].started_at >= runs[1].started_at
        assert runs[0].trace_id
        assert runs[0].status == "completed"
        assert runs[1].status == "completed"

    def test_index_service_exposes_semantic_artifact_status(
        self,
        source_service: SourceService,
        index_service: IndexService,
        hnsw_path: Path,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.rebuild_index(source.source_root_id)

        artifact_status = index_service.get_artifact_status()
        status = index_service.get_index_status()

        assert artifact_status.artifact_name == "dense_hnsw"
        assert not hasattr(artifact_status, "status")
        assert artifact_status.freshness_status == "ready"
        assert artifact_status.semantic_mode == LocalSemanticEmbedder.MODEL_NAME
        assert artifact_status.degraded is False
        assert artifact_status.degraded_reason is None
        assert artifact_status.generation >= 1
        assert artifact_status.committed_generation == artifact_status.generation
        assert artifact_status.committed_readable is True
        assert artifact_status.committed_readability_reason is None
        assert artifact_status.build_in_progress is False
        assert artifact_status.namespace_path == str(hnsw_path)
        assert artifact_status.committed_artifact_path is not None
        assert artifact_status.committed_artifact_path != artifact_status.namespace_path
        committed_path = Path(artifact_status.committed_artifact_path)
        assert committed_path.exists()
        assert committed_path.name == hnsw_path.name
        assert committed_path.parent.parent == hnsw_path.parent / ".dense_hnsw_bundles"
        assert artifact_status.embedder_model == LocalSemanticEmbedder.MODEL_NAME
        assert artifact_status.embedder_dim == LocalSemanticEmbedder.DIM
        assert artifact_status.embedder_signature

        assert status.semantic_mode == artifact_status.semantic_mode
        assert not hasattr(status, "hnsw_status")
        assert status.semantic_freshness_status == artifact_status.freshness_status
        assert status.semantic_degraded is False
        assert status.semantic_degraded_reason is None
        assert status.semantic_namespace_path == artifact_status.namespace_path
        assert status.semantic_committed_artifact_path == artifact_status.committed_artifact_path
        assert status.semantic_committed_generation == artifact_status.committed_generation
        assert status.semantic_committed_readable is True
        assert status.semantic_committed_readability_reason is None
        assert status.semantic_build_in_progress is False
        assert status.semantic_build_started_at is None
        assert status.semantic_build_lease_expires_at is None

    def test_index_service_derives_runtime_artifact_path_without_explicit_hnsw(
        self,
        engine: Engine,
        db_path: Path,
        corpus_copy: Path,
    ) -> None:
        source = SourceService(engine).add_source(corpus_copy)
        with OpenDocsRuntime(engine) as runtime:
            service = runtime.build_index_service()
            service.rebuild_index(source.source_root_id)
            artifact_status = service.get_artifact_status()
        expected_namespace = resolve_runtime_hnsw_path(resolve_runtime_root_from_db_path(db_path))

        assert artifact_status.freshness_status == "ready"
        assert artifact_status.namespace_path == str(expected_namespace)
        assert artifact_status.committed_artifact_path is not None
        committed_path = Path(artifact_status.committed_artifact_path)
        assert committed_path.exists()
        assert committed_path.name == expected_namespace.name
        assert committed_path.parent.parent == expected_namespace.parent / ".dense_hnsw_bundles"

    def test_public_artifact_status_demotes_ready_row_when_runtime_dirty(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        hnsw_path: Path,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.rebuild_index(source.source_root_id)

        semantic_indexer = SemanticIndexer(engine, hnsw_path=hnsw_path)
        assert semantic_indexer.hnsw_manager is not None
        semantic_indexer.hnsw_manager.mark_dirty()

        artifact_status = index_service.get_artifact_status()
        with session_scope(engine) as session:
            row = session.execute(
                text(
                    "SELECT status, last_reason FROM index_artifacts "
                    "WHERE artifact_name = 'dense_hnsw'"
                )
            ).one()

        assert artifact_status.freshness_status == "stale"
        assert artifact_status.degraded is True
        assert artifact_status.degraded_reason == "dirty_flag_present"
        assert artifact_status.committed_readable is True
        assert artifact_status.committed_readability_reason is None
        assert row[0] == "stale"
        assert row[1] == "dirty_flag_present"

    def test_ready_public_status_stays_ready_while_build_lease_is_active(
        self,
        source_service: SourceService,
        index_service: IndexService,
        indexing_runtime: OpenDocsRuntime,
        engine: Engine,
        hnsw_path: Path,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.rebuild_index(source.source_root_id)

        active_started_at = utcnow_naive() - timedelta(minutes=1)
        with session_scope(engine) as session:
            repo = IndexArtifactRepository(session)
            repo.upsert(
                "dense_hnsw",
                status="ready",
                active_build_token="active-token",
                build_started_at=active_started_at,
                lease_expires_at=active_started_at + timedelta(minutes=5),
                last_reason="service_rebuild_index",
            )

        artifact_status = index_service.get_artifact_status()
        response = indexing_runtime.build_search_service().search("report")

        assert response.results
        assert artifact_status.freshness_status == "ready"
        assert artifact_status.degraded is False
        assert artifact_status.degraded_reason is None
        assert artifact_status.committed_readable is True
        assert artifact_status.build_in_progress is True

    def test_public_artifact_status_expires_orphaned_build_lease_without_hiding_ready_bundle(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        hnsw_path: Path,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.rebuild_index(source.source_root_id)

        expired_at = utcnow_naive() - timedelta(minutes=10)
        with session_scope(engine) as session:
            repo = IndexArtifactRepository(session)
            repo.upsert(
                "dense_hnsw",
                status="ready",
                active_build_token="expired-token",
                build_started_at=expired_at - timedelta(minutes=1),
                lease_expires_at=expired_at,
                last_reason="service_rebuild_index",
            )

        artifact_status = index_service.get_artifact_status()
        with session_scope(engine) as session:
            row = session.execute(
                text(
                    "SELECT status, active_build_token, lease_expires_at, last_reason "
                    "FROM index_artifacts WHERE artifact_name = 'dense_hnsw'"
                )
            ).one()

        assert artifact_status.freshness_status == "ready"
        assert artifact_status.degraded is False
        assert artifact_status.degraded_reason is None
        assert artifact_status.committed_readable is True
        assert artifact_status.build_in_progress is False
        assert row[0] == "ready"
        assert row[1] is None
        assert row[2] is None
        assert row[3] == "build_lease_expired"

    def test_build_lease_claim_is_exclusive_until_expiry(
        self,
        engine: Engine,
        hnsw_path: Path,
    ) -> None:
        now = utcnow_naive()
        future = now + timedelta(minutes=5)
        later = now + timedelta(minutes=6)
        model_name = LocalSemanticEmbedder.MODEL_NAME
        dim = LocalSemanticEmbedder.DIM
        signature = LocalSemanticEmbedder(model_path=None).fingerprint

        with session_scope(engine) as session:
            repo = IndexArtifactRepository(session)
            assert repo.try_claim_build(
                "dense_hnsw",
                namespace_path=str(hnsw_path),
                embedder_model=model_name,
                embedder_dim=dim,
                embedder_signature=signature,
                build_token="token-a",
                build_started_at=now,
                lease_expires_at=future,
                reason="claim-a",
            )

        with session_scope(engine) as session:
            repo = IndexArtifactRepository(session)
            assert not repo.try_claim_build(
                "dense_hnsw",
                namespace_path=str(hnsw_path),
                embedder_model=model_name,
                embedder_dim=dim,
                embedder_signature=signature,
                build_token="token-b",
                build_started_at=now + timedelta(seconds=1),
                lease_expires_at=future,
                reason="claim-b",
            )

        with session_scope(engine) as session:
            repo = IndexArtifactRepository(session)
            assert repo.expire_build_lease(
                "dense_hnsw",
                expired_before=later,
                reason="lease-expired",
            )
            assert repo.try_claim_build(
                "dense_hnsw",
                namespace_path=str(hnsw_path),
                embedder_model=model_name,
                embedder_dim=dim,
                embedder_signature=signature,
                build_token="token-c",
                build_started_at=later,
                lease_expires_at=later + timedelta(minutes=5),
                reason="claim-c",
            )

    def test_public_status_and_committed_readability_are_exposed_as_separate_contracts(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        hnsw_path: Path,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.rebuild_index(source.source_root_id)

        started_at = utcnow_naive() - timedelta(minutes=1)
        with session_scope(engine) as session:
            repo = IndexArtifactRepository(session)
            repo.upsert(
                "dense_hnsw",
                status="stale",
                active_build_token="active-stale-build",
                build_started_at=started_at,
                lease_expires_at=started_at + timedelta(minutes=5),
                last_reason="watcher_modified_change",
            )

        artifact_status = index_service.get_artifact_status()
        status = index_service.get_index_status()

        assert artifact_status.freshness_status == "stale"
        assert artifact_status.committed_readable is True
        assert artifact_status.committed_readability_reason is None
        assert artifact_status.degraded is True
        assert artifact_status.degraded_reason == "watcher_modified_change"
        assert status.semantic_freshness_status == "stale"
        assert status.semantic_committed_readable is True
        assert status.semantic_committed_readability_reason is None
        assert status.semantic_committed_generation >= 1

    def test_public_status_contract_marks_committed_generation_unreadable_when_bundle_is_missing(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.rebuild_index(source.source_root_id)

        artifact_status_before = index_service.get_artifact_status()
        assert artifact_status_before.committed_artifact_path is not None
        committed_bundle_path = Path(artifact_status_before.committed_artifact_path)
        committed_bundle_path.unlink()

        artifact_status = index_service.get_artifact_status()
        status = index_service.get_index_status()

        assert artifact_status.freshness_status == "stale"
        assert artifact_status.committed_readable is False
        assert artifact_status.committed_readability_reason == "index_file_missing"
        assert artifact_status.degraded is True
        assert artifact_status.degraded_reason == "index_file_missing"
        assert status.semantic_committed_readable is False
        assert status.semantic_committed_readability_reason == "index_file_missing"

    def test_rebuild_records_committed_and_retained_generation_lifecycle(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        index_service.rebuild_index(source.source_root_id)

        changed = corpus_copy / "generation_retained_note.md"
        changed.write_text("Project budget approved for generation retention.", encoding="utf-8")
        index_service.update_index_for_changes(source.source_root_id)

        with session_scope(engine) as session:
            generations = IndexArtifactRepository(session).list_generations("dense_hnsw", include_deleted=True)

        assert len(generations) >= 2
        assert generations[0].state == "committed"
        assert generations[0].delete_after is None
        assert generations[1].state == "retained"
        assert generations[1].retired_at is not None
        assert generations[1].delete_after is not None
        assert Path(generations[0].bundle_path).exists()
        assert Path(generations[1].bundle_path).exists()

    def test_generation_gc_owner_prunes_expired_retained_generation_without_status_query(
        self,
        engine: Engine,
        hnsw_path: Path,
        corpus_copy: Path,
    ) -> None:
        runtime = OpenDocsRuntime(
            engine,
            hnsw_path=hnsw_path,
            generation_gc_idle_poll_seconds=0.05,
        )
        source_service = SourceService(engine, hnsw_path=hnsw_path, runtime=runtime)
        index_service = runtime.build_index_service()
        try:
            source = source_service.add_source(corpus_copy)
            index_service.rebuild_index(source.source_root_id)

            changed = corpus_copy / "generation_gc_note.md"
            changed.write_text(
                "Budget approval changed to force a new committed generation.",
                encoding="utf-8",
            )
            index_service.update_index_for_changes(source.source_root_id)
            assert runtime.build_search_service().search("budget").results

            with session_scope(engine) as session:
                retained = IndexArtifactRepository(session).list_generations(
                    "dense_hnsw",
                    include_deleted=True,
                )[1]
                retained_bundle_path = Path(retained.bundle_path)
                session.execute(
                    text(
                        "UPDATE index_artifact_generations "
                        "SET delete_after = :delete_after "
                        "WHERE artifact_name = 'dense_hnsw' AND generation = :generation"
                    ),
                    {
                        "delete_after": (utcnow_naive() - timedelta(minutes=1)).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        "generation": retained.generation,
                    },
                )

            assert retained_bundle_path.exists()
            deleted_generation = None
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                with session_scope(engine) as session:
                    generations = IndexArtifactRepository(session).list_generations(
                        "dense_hnsw",
                        include_deleted=True,
                    )
                deleted_generation = next(
                    generation
                    for generation in generations
                    if generation.generation == retained.generation
                )
                if deleted_generation.state == "deleted":
                    break
                time.sleep(0.05)

            assert deleted_generation is not None
            assert deleted_generation.state == "deleted"
            assert deleted_generation.deleted_at is not None
            assert retained_bundle_path.exists() is False
        finally:
            index_service.close()
            runtime.close()

    def test_runtime_reuses_single_generation_gc_owner_for_same_engine_and_namespace(
        self,
        engine: Engine,
        hnsw_path: Path,
    ) -> None:
        baseline = _count_generation_gc_workers()
        runtime_a = OpenDocsRuntime(
            engine,
            hnsw_path=hnsw_path,
            generation_gc_idle_poll_seconds=0.05,
        )
        runtime_b = OpenDocsRuntime(
            engine,
            hnsw_path=hnsw_path,
            generation_gc_idle_poll_seconds=0.05,
        )
        try:
            assert runtime_a.semantic_indexer is runtime_b.semantic_indexer

            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline and _count_generation_gc_workers() < baseline + 1:
                time.sleep(0.01)

            assert _count_generation_gc_workers() == baseline + 1
        finally:
            runtime_b.close()
            runtime_a.close()

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and _count_generation_gc_workers() > baseline:
            time.sleep(0.01)

        assert _count_generation_gc_workers() == baseline

    def test_runtime_reuses_owner_for_same_database_identity_across_engine_instances(
        self,
        db_path: Path,
        hnsw_path: Path,
    ) -> None:
        baseline = _count_generation_gc_workers()
        engine_a = build_sqlite_engine(db_path)
        engine_b = build_sqlite_engine(db_path)
        runtime_a = OpenDocsRuntime(
            engine_a,
            hnsw_path=hnsw_path,
            generation_gc_idle_poll_seconds=0.05,
        )
        runtime_b = OpenDocsRuntime(
            engine_b,
            hnsw_path=hnsw_path,
            generation_gc_idle_poll_seconds=0.05,
        )
        try:
            assert runtime_a.semantic_indexer is runtime_b.semantic_indexer

            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline and _count_generation_gc_workers() < baseline + 1:
                time.sleep(0.01)

            assert _count_generation_gc_workers() == baseline + 1
        finally:
            runtime_b.close()
            runtime_a.close()

    def test_runtime_close_invalidates_services_built_from_that_handle(
        self,
        engine: Engine,
        hnsw_path: Path,
        corpus_copy: Path,
    ) -> None:
        runtime = OpenDocsRuntime(engine, hnsw_path=hnsw_path)
        try:
            source_service = SourceService(engine, hnsw_path=hnsw_path, runtime=runtime)
            index_service = runtime.build_index_service()
            search_service = runtime.build_search_service()

            source = source_service.add_source(corpus_copy)
            index_service.rebuild_index(source.source_root_id)
            assert search_service.search("report").results

            runtime.close()

            with pytest.raises(RuntimeClosedError):
                runtime.build_search_service()
            with pytest.raises(RuntimeClosedError):
                index_service.get_index_status()
            with pytest.raises(RuntimeClosedError):
                search_service.search("report")
        finally:
            index_service.close()
            runtime.close()

    def test_source_service_rejects_index_relevant_update_without_explicit_runtime_owner(
        self,
        engine: Engine,
        hnsw_path: Path,
        corpus_copy: Path,
    ) -> None:
        service = SourceService(engine, hnsw_path=hnsw_path)
        source = service.add_source(corpus_copy, reindex_on_change=False)

        with pytest.raises(RuntimeOwnershipError, match="explicit OpenDocsRuntime owner"):
            service.update_source_by_path(corpus_copy, recursive=False)

        reloaded = service.get_source(source.source_root_id)
        assert reloaded is not None
        assert reloaded.recursive is True

    def test_semantic_query_hits_synonym_without_keyword_in_filename(
        self,
        source_service: SourceService,
        index_service: IndexService,
        engine: Engine,
        hnsw_path: Path,
        corpus_copy: Path,
    ) -> None:
        source = source_service.add_source(corpus_copy)
        neutral_doc = corpus_copy / "neutral_note.md"
        neutral_doc.write_text(
            "# Neutral\n\n"
            "Project budget approved for the next quarter.\n"
            "Project budget review stays within target.\n"
            "Quarterly funding discussion remains stable.\n",
            encoding="utf-8",
        )
        index_service.rebuild_index(source.source_root_id)

        semantic_indexer = SemanticIndexer(engine, hnsw_path=hnsw_path)
        hits = semantic_indexer.query("cost plan", top_k=10)

        assert hits
        lowered_name = neutral_doc.name.lower()
        assert "budget" not in lowered_name
        assert "plan" not in lowered_name
        assert "cost" not in lowered_name

        with session_scope(engine) as session:
            target_chunk_ids = {
                row[0]
                for row in session.execute(
                    text(
                        "SELECT c.chunk_id "
                        "FROM chunks c "
                        "JOIN documents d ON d.doc_id = c.doc_id "
                        "WHERE d.path = :path"
                    ),
                    {"path": str(neutral_doc.resolve())},
                ).fetchall()
            }

        assert target_chunk_ids
        assert any(hit.chunk_id in target_chunk_ids for hit in hits)

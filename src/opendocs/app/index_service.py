"""Application service for index orchestration (S3-T02/T03/T04)."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from opendocs.app._audit_helpers import create_audit_record, flush_audit_to_jsonl
from opendocs.app.source_service import SourceService
from opendocs.domain.models import (
    AuditLogModel,
    ChunkModel,
    DocumentModel,
    ScanRunModel,
    SourceRootModel,
)
from opendocs.indexing.chunker import Chunker
from opendocs.indexing.index_builder import IndexBatchResult, IndexBuilder
from opendocs.indexing.scanner import ScanResult
from opendocs.indexing.semantic_indexer import SemanticArtifactStatus
from opendocs.indexing.watcher import IndexWatcher
from opendocs.parsers import create_default_registry
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import SourceRepository

if TYPE_CHECKING:
    from opendocs.app.runtime import OpenDocsRuntime


@dataclass(frozen=True)
class IndexedScanContext:
    source: SourceRootModel
    scan: ScanResult
    scan_run: ScanRunModel


@dataclass(frozen=True)
class IndexStatus:
    watch_changes_enabled: bool
    watcher_running: bool
    active_source_count: int
    watched_source_count: int
    watched_paths: tuple[str, ...]
    total_document_count: int
    active_document_count: int
    total_chunk_count: int
    semantic_mode: str
    semantic_freshness_status: str
    semantic_degraded: bool
    semantic_degraded_reason: str | None
    semantic_namespace_path: str | None
    semantic_committed_artifact_path: str | None
    semantic_committed_generation: int
    semantic_committed_readable: bool
    semantic_committed_readability_reason: str | None
    semantic_build_in_progress: bool
    semantic_build_started_at: datetime | None
    semantic_build_lease_expires_at: datetime | None
    last_scan_status: str | None
    last_scan_finished_at: datetime | None


class IndexService:
    """Orchestrate full/incremental/rebuild indexing operations."""

    def __init__(
        self,
        runtime: OpenDocsRuntime,
        *,
        watch_changes: bool = True,
    ) -> None:
        self._runtime = runtime
        self._engine = runtime.engine
        registry = create_default_registry()
        chunker = Chunker()
        self._semantic_indexer = runtime.semantic_indexer
        self._embedder = self._semantic_indexer.embedder
        self._registry = registry
        self._watch_changes = watch_changes
        self._watcher: IndexWatcher | None = None

        self._builder = IndexBuilder(
            self._engine,
            registry,
            chunker,
            hnsw_manager=self._semantic_indexer.hnsw_manager,
            embedder=self._embedder,
        )
        self._hnsw = self._semantic_indexer.hnsw_manager
        self._source_service = SourceService(
            self._engine,
            hnsw_path=self._semantic_indexer.hnsw_path,
            runtime=runtime,
        )

    def _ensure_runtime_open(self) -> None:
        self._runtime.ensure_open()

    def start_watching_active_sources(self, *, debounce_seconds: float = 1.0) -> IndexStatus:
        """Start the runtime watcher for all active sources."""
        self._ensure_runtime_open()
        self.stop_watching()

        if not self._watch_changes:
            return self.get_index_status()

        sources = self._source_service.list_sources()
        if not sources:
            return self.get_index_status()

        watcher = IndexWatcher(
            self._engine,
            self._builder,
            self._registry,
            debounce_seconds=debounce_seconds,
            dense_compensator=self._semantic_indexer.compensate_if_dirty,
        )
        watched_count = watcher.start(sources)
        if watched_count == 0:
            return self.get_index_status()

        self._watcher = watcher
        return self.get_index_status()

    def stop_watching(self) -> None:
        if self._watcher is None:
            return
        self._watcher.stop()
        self._watcher = None

    def get_index_status(self) -> IndexStatus:
        """Report the current indexing and watcher runtime state."""
        self._ensure_runtime_open()
        with session_scope(self._engine) as session:
            active_source_count = (
                session.scalar(
                    select(func.count())
                    .select_from(SourceRootModel)
                    .where(SourceRootModel.is_active.is_(True))
                )
                or 0
            )
            total_document_count = (
                session.scalar(select(func.count()).select_from(DocumentModel)) or 0
            )
            active_document_count = (
                session.scalar(
                    select(func.count())
                    .select_from(DocumentModel)
                    .where(DocumentModel.is_deleted_from_fs.is_(False))
                )
                or 0
            )
            total_chunk_count = session.scalar(select(func.count()).select_from(ChunkModel)) or 0
            last_scan = session.scalar(
                select(ScanRunModel).order_by(ScanRunModel.started_at.desc()).limit(1)
            )
        artifact_status = self.get_artifact_status()

        watched_paths: tuple[str, ...] = ()
        if self._watcher is not None:
            watched_paths = self._watcher.watched_paths

        return IndexStatus(
            watch_changes_enabled=self._watch_changes,
            watcher_running=self._watcher is not None and self._watcher.is_running(),
            active_source_count=int(active_source_count),
            watched_source_count=len(watched_paths),
            watched_paths=watched_paths,
            total_document_count=int(total_document_count),
            active_document_count=int(active_document_count),
            total_chunk_count=int(total_chunk_count),
            semantic_mode=artifact_status.semantic_mode,
            semantic_freshness_status=artifact_status.freshness_status,
            semantic_degraded=artifact_status.degraded,
            semantic_degraded_reason=artifact_status.degraded_reason,
            semantic_namespace_path=artifact_status.namespace_path,
            semantic_committed_artifact_path=artifact_status.committed_artifact_path,
            semantic_committed_generation=artifact_status.committed_generation,
            semantic_committed_readable=artifact_status.committed_readable,
            semantic_committed_readability_reason=artifact_status.committed_readability_reason,
            semantic_build_in_progress=artifact_status.build_in_progress,
            semantic_build_started_at=artifact_status.build_started_at,
            semantic_build_lease_expires_at=artifact_status.build_lease_expires_at,
            last_scan_status=last_scan.status if last_scan is not None else None,
            last_scan_finished_at=last_scan.finished_at if last_scan is not None else None,
        )

    def get_artifact_status(self) -> SemanticArtifactStatus:
        """Expose the current dense semantic artifact status owned by S3."""
        self._ensure_runtime_open()
        return self._semantic_indexer.get_artifact_status()

    def full_index_source(self, source_root_id: str) -> IndexBatchResult:
        """First-time full index: scan → index all → detect deleted."""
        self._ensure_runtime_open()
        self._semantic_indexer.ensure_ready()

        scan_ctx = self._scan_for_index(source_root_id)
        trace_id = scan_ctx.scan_run.trace_id
        result = self._builder.index_batch(
            scan_ctx.scan.included,
            source_root_id=source_root_id,
            trace_id=trace_id,
            force=False,
        )

        # Detect deleted files
        self._soft_delete_missing(source_root_id, scan_ctx.scan, trace_id)

        # HNSW compensation
        if self._hnsw:
            result.dense_reconcile_status = self._semantic_indexer.compensate_if_dirty(
                reason="full_index_compensation"
            )
        self._semantic_indexer.request_generation_lifecycle_reconcile()

        audit_record: AuditLogModel | None = None
        with session_scope(self._engine) as session:
            audit_record = create_audit_record(
                session,
                actor="system",
                operation="index_full",
                target_type="index_run",
                target_id=scan_ctx.scan_run.scan_run_id,
                result="success" if result.failed_count == 0 else "failure",
                detail_json={
                    "source_root_id": source_root_id,
                    "scan_run_id": scan_ctx.scan_run.scan_run_id,
                    "total": result.total,
                    "success": result.success_count,
                    "partial": result.partial_count,
                    "failed": result.failed_count,
                    "skipped": result.skipped_count,
                    "dense_reconcile_status": result.dense_reconcile_status,
                    "duration_sec": result.duration_sec,
                },
                trace_id=trace_id,
            )
        if audit_record is not None:
            flush_audit_to_jsonl(audit_record)

        return result

    def update_index_for_changes(self, source_root_id: str) -> IndexBatchResult:
        """Incremental update: scan → diff with DB → index changed."""
        self._ensure_runtime_open()
        self._semantic_indexer.ensure_ready()

        scan_ctx = self._scan_for_index(source_root_id)
        trace_id = scan_ctx.scan_run.trace_id
        # force=False means hash comparison skips unchanged files
        result = self._builder.index_batch(
            scan_ctx.scan.included,
            source_root_id=source_root_id,
            trace_id=trace_id,
            force=False,
        )

        self._soft_delete_missing(source_root_id, scan_ctx.scan, trace_id)

        # HNSW compensation
        if self._hnsw:
            result.dense_reconcile_status = self._semantic_indexer.compensate_if_dirty(
                reason="incremental_compensation"
            )
        self._semantic_indexer.request_generation_lifecycle_reconcile()

        # Batch-level audit for incremental update (mirrors rebuild_index pattern)
        audit_record: AuditLogModel | None = None
        with session_scope(self._engine) as session:
            audit_record = create_audit_record(
                session,
                actor="system",
                operation="index_incremental",
                target_type="index_run",
                target_id=scan_ctx.scan_run.scan_run_id,
                result="success" if result.failed_count == 0 else "failure",
                detail_json={
                    "source_root_id": source_root_id,
                    "scan_run_id": scan_ctx.scan_run.scan_run_id,
                    "total": result.total,
                    "success": result.success_count,
                    "failed": result.failed_count,
                    "skipped": result.skipped_count,
                    "dense_reconcile_status": result.dense_reconcile_status,
                    "duration_sec": result.duration_sec,
                },
                trace_id=trace_id,
            )
        if audit_record is not None:
            flush_audit_to_jsonl(audit_record)

        return result

    def rebuild_index(self, source_root_id: str) -> IndexBatchResult:
        """Full rebuild: force=True, no hash skip, HNSW rebuild from DB."""
        self._ensure_runtime_open()
        self._semantic_indexer.ensure_ready()

        scan_ctx = self._scan_for_index(source_root_id)
        trace_id = scan_ctx.scan_run.trace_id
        result = self._builder.index_batch(
            scan_ctx.scan.included,
            source_root_id=source_root_id,
            trace_id=trace_id,
            force=True,  # ← unconditional reprocess
        )

        self._soft_delete_missing(source_root_id, scan_ctx.scan, trace_id)

        # Always rebuild HNSW from DB on full rebuild
        if self._hnsw:
            result.dense_reconcile_status = self._semantic_indexer.rebuild(
                reason="service_rebuild_index"
            )
        self._semantic_indexer.request_generation_lifecycle_reconcile()

        # Audit for the rebuild
        audit_record: AuditLogModel | None = None
        with session_scope(self._engine) as session:
            audit_record = create_audit_record(
                session,
                actor="system",
                operation="index_rebuild",
                target_type="index_run",
                target_id=scan_ctx.scan_run.scan_run_id,
                result="success" if result.failed_count == 0 else "failure",
                detail_json={
                    "source_root_id": source_root_id,
                    "scan_run_id": scan_ctx.scan_run.scan_run_id,
                    "total": result.total,
                    "success": result.success_count,
                    "failed": result.failed_count,
                    "skipped": result.skipped_count,
                    "dense_reconcile_status": result.dense_reconcile_status,
                    "duration_sec": result.duration_sec,
                },
                trace_id=trace_id,
            )
        if audit_record is not None:
            flush_audit_to_jsonl(audit_record)

        return result

    def close(self) -> None:
        self.stop_watching()

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            self.close()
        except Exception:
            pass

    def _load_source(self, source_root_id: str) -> object:
        """Load source root from DB."""
        from opendocs.exceptions import SourceNotFoundError

        with session_scope(self._engine) as session:
            source = SourceRepository(session).get_by_id(source_root_id)
            if source is None:
                raise SourceNotFoundError(f"source not found: {source_root_id}")
            # Detach from session
            return source

    def _scan_for_index(self, source_root_id: str) -> IndexedScanContext:
        """Single scan entrypoint for full/incremental/rebuild indexing."""
        source = self._load_source(source_root_id)
        scan, scan_run = self._source_service.scan_source(source_root_id)
        return IndexedScanContext(
            source=source,
            scan=scan,
            scan_run=scan_run,
        )

    def _soft_delete_missing(self, source_root_id: str, scan: object, trace_id: str) -> None:
        """Mark documents as deleted if they're in DB but not on disk."""
        from opendocs.indexing.scanner import ScanResult

        assert isinstance(scan, ScanResult)
        disk_paths = {str(f.path) for f in scan.included}
        error_paths = [path for path, _ in scan.errors]

        with session_scope(self._engine) as session:
            stmt = (
                select(DocumentModel)
                .where(DocumentModel.source_root_id == source_root_id)
                .where(DocumentModel.is_deleted_from_fs.is_(False))
            )
            db_docs = list(session.scalars(stmt))
            missing_ids = [
                d.doc_id
                for d in db_docs
                if d.path not in disk_paths
                and not self._is_covered_by_scan_error(d.path, error_paths)
            ]

        for doc_id in missing_ids:
            self._builder.remove_document(doc_id, trace_id=trace_id, soft_delete=True)

    @staticmethod
    def _is_covered_by_scan_error(doc_path: str, error_paths: list[str]) -> bool:
        """Do not interpret unreadable paths as deleted documents."""
        resolved_doc = Path(doc_path).resolve(strict=False)
        for error_path in error_paths:
            resolved_error = Path(error_path).resolve(strict=False)
            if resolved_doc == resolved_error or resolved_doc.is_relative_to(resolved_error):
                return True
        return False

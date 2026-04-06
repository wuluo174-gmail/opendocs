"""Application service for index orchestration (S3-T02/T03/T04)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from opendocs.app._audit_helpers import create_audit_record, flush_audit_to_jsonl
from opendocs.app.source_service import SourceService
from opendocs.domain.models import (
    AuditLogModel,
    ChunkModel,
    DocumentModel,
    IndexArtifactModel,
    ScanRunModel,
    SourceRootModel,
)
from opendocs.indexing.chunker import Chunker
from opendocs.indexing.hnsw_manager import HnswManager
from opendocs.indexing.index_builder import IndexBatchResult, IndexBuilder
from opendocs.indexing.scanner import Scanner, ScanResult
from opendocs.indexing.watcher import IndexWatcher
from opendocs.parsers import create_default_registry
from opendocs.retrieval.embedder import LocalNgramEmbedder
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import SourceRepository

logger = logging.getLogger(__name__)


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
    hnsw_status: str
    last_scan_status: str | None
    last_scan_finished_at: datetime | None


class IndexService:
    """Orchestrate full/incremental/rebuild indexing operations."""

    def __init__(
        self,
        engine: Engine,
        *,
        hnsw_path: Path | None = None,
        watch_changes: bool = True,
    ) -> None:
        self._engine = engine
        registry = create_default_registry()
        chunker = Chunker()
        self._embedder = LocalNgramEmbedder()
        self._registry = registry
        self._scanner = Scanner(registry)
        self._watch_changes = watch_changes
        self._watcher: IndexWatcher | None = None

        hnsw: HnswManager | None = None
        if hnsw_path is not None:
            hnsw = HnswManager(hnsw_path, dim=self._embedder.dim)

        self._builder = IndexBuilder(
            engine, registry, chunker, hnsw_manager=hnsw, embedder=self._embedder
        )
        self._hnsw = hnsw
        self._source_service = SourceService(engine)

    def start_watching_active_sources(self, *, debounce_seconds: float = 1.0) -> IndexStatus:
        """Start the runtime watcher for all active sources."""
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
            artifact = session.get(IndexArtifactModel, "dense_hnsw")

        if self._hnsw is None:
            hnsw_status = "unconfigured"
        elif artifact is None:
            hnsw_status = "stale"
        else:
            hnsw_status = artifact.status

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
            hnsw_status=hnsw_status,
            last_scan_status=last_scan.status if last_scan is not None else None,
            last_scan_finished_at=last_scan.finished_at if last_scan is not None else None,
        )

    def full_index_source(self, source_root_id: str) -> IndexBatchResult:
        """First-time full index: scan → index all → detect deleted."""
        if self._hnsw:
            self._hnsw.check_and_repair(self._engine, embedder=self._embedder)

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
        if self._hnsw and self._hnsw.is_dirty():
            try:
                self._hnsw.rebuild_from_db(
                    self._engine,
                    embedder=self._embedder,
                    reason="full_index_compensation",
                )
            except Exception:
                result.hnsw_status = "degraded"
                logger.warning("HNSW compensation rebuild failed")

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
                    "hnsw_status": result.hnsw_status,
                    "duration_sec": result.duration_sec,
                },
                trace_id=trace_id,
            )
        if audit_record is not None:
            flush_audit_to_jsonl(audit_record)

        return result

    def update_index_for_changes(self, source_root_id: str) -> IndexBatchResult:
        """Incremental update: scan → diff with DB → index changed."""
        if self._hnsw:
            self._hnsw.check_and_repair(self._engine, embedder=self._embedder)

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
        if self._hnsw and self._hnsw.is_dirty():
            try:
                self._hnsw.rebuild_from_db(
                    self._engine,
                    embedder=self._embedder,
                    reason="incremental_compensation",
                )
            except Exception:
                result.hnsw_status = "degraded"
                logger.warning("HNSW compensation rebuild failed")

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
                    "hnsw_status": result.hnsw_status,
                    "duration_sec": result.duration_sec,
                },
                trace_id=trace_id,
            )
        if audit_record is not None:
            flush_audit_to_jsonl(audit_record)

        return result

    def rebuild_index(self, source_root_id: str) -> IndexBatchResult:
        """Full rebuild: force=True, no hash skip, HNSW rebuild from DB."""
        if self._hnsw:
            self._hnsw.check_and_repair(self._engine, embedder=self._embedder)

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
            try:
                self._hnsw.rebuild_from_db(
                    self._engine,
                    embedder=self._embedder,
                    reason="service_rebuild_index",
                )
            except Exception:
                result.hnsw_status = "degraded"
                logger.warning("HNSW rebuild from DB failed")

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
                    "hnsw_status": result.hnsw_status,
                    "duration_sec": result.duration_sec,
                },
                trace_id=trace_id,
            )
        if audit_record is not None:
            flush_audit_to_jsonl(audit_record)

        return result

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

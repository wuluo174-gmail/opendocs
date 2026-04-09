"""S3 semantic index adapter for dense artifact ownership and visibility."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import Engine

from opendocs.exceptions import ArtifactBuildBusyError
from opendocs.indexing.hnsw_manager import (
    CommittedBundleSnapshot,
    HnswManager,
    NullHnswManager,
)
from opendocs.retrieval.embedder import LocalSemanticEmbedder
from opendocs.runtime_paths import (
    build_runtime_paths,
    resolve_runtime_root_from_db_path,
)
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import IndexArtifactRepository
from opendocs.utils.time import utcnow_naive

logger = logging.getLogger(__name__)

_UNCONFIGURED_REASON = "hnsw_unconfigured"


@dataclass(frozen=True)
class SemanticArtifactStatus:
    """Visible status of the dense semantic artifact owned by S3."""

    artifact_name: str
    freshness_status: str
    semantic_mode: str
    degraded: bool
    degraded_reason: str | None
    namespace_path: str | None
    committed_artifact_path: str | None
    embedder_model: str
    embedder_dim: int
    embedder_signature: str
    generation: int
    committed_generation: int
    committed_readable: bool
    committed_readability_reason: str | None
    build_in_progress: bool
    build_started_at: datetime | None
    build_lease_expires_at: datetime | None
    last_error: str | None
    last_reason: str | None
    last_built_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class SemanticQueryHit:
    """Low-level dense query hit used by S3 validation tests."""

    chunk_id: str
    distance: float


class _GenerationLifecycleCoordinator:
    """Own retained-generation GC independently from status/query entrypoints."""

    def __init__(
        self,
        engine: Engine,
        hnsw_manager: HnswManager | None,
        *,
        idle_poll_seconds: float,
    ) -> None:
        self._engine = engine
        self._hnsw_manager = hnsw_manager
        self._idle_poll_seconds = max(0.05, idle_poll_seconds)
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._worker: threading.Thread | None = None
        self._stop_requested = False
        self._pending = True

    def start(self) -> None:
        if self._hnsw_manager is None:
            return
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._stop_requested = False
            self._pending = True
            self._worker = threading.Thread(
                target=self._run,
                name="OpenDocsGenerationLifecycleWorker",
                daemon=True,
            )
            self._worker.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_requested = True
            self._cv.notify_all()
            worker = self._worker
        if worker is not None:
            worker.join(timeout=5)
        with self._lock:
            self._worker = None
            self._pending = False

    def request(self) -> None:
        if self._hnsw_manager is None:
            return
        with self._lock:
            self._pending = True
            self._cv.notify_all()

    def _run(self) -> None:
        while True:
            with self._lock:
                while not self._pending and not self._stop_requested:
                    timeout = self._next_wait_timeout()
                    self._cv.wait(timeout=timeout)
                    if timeout is not None and not self._pending:
                        break
                if self._stop_requested:
                    return
                self._pending = False
            try:
                assert self._hnsw_manager is not None
                self._hnsw_manager.reconcile_generation_lifecycle(self._engine)
            except Exception:
                logger.warning("Generation lifecycle reconcile failed", exc_info=True)

    def _next_wait_timeout(self) -> float | None:
        if self._hnsw_manager is None:
            return None
        next_due_at = self._hnsw_manager.next_generation_gc_deadline(self._engine)
        if next_due_at is None:
            return self._idle_poll_seconds
        remaining = (next_due_at - utcnow_naive()).total_seconds()
        if remaining <= 0:
            return 0.0
        return min(self._idle_poll_seconds, remaining)

    def tighten_idle_poll_seconds(self, idle_poll_seconds: float) -> None:
        candidate = max(0.05, idle_poll_seconds)
        with self._lock:
            if candidate < self._idle_poll_seconds:
                self._idle_poll_seconds = candidate
                self._cv.notify_all()


def resolve_semantic_namespace_path(
    engine: Engine,
    *,
    preferred_path: str | Path | None = None,
) -> Path | None:
    """Resolve the canonical dense artifact namespace from runtime ownership rules."""
    if preferred_path is not None:
        return Path(preferred_path).expanduser().resolve()

    database_path = getattr(engine.url, "database", None)
    if not database_path:
        return None

    runtime_root = resolve_runtime_root_from_db_path(database_path)
    return build_runtime_paths(app_root=runtime_root, db_path=database_path).hnsw_path


class SemanticIndexer:
    """Own the S3 dense artifact wiring, visibility, and minimal query path."""

    def __init__(
        self,
        engine: Engine,
        *,
        hnsw_path: Path | None,
        enable_generation_gc_owner: bool = False,
        generation_gc_idle_poll_seconds: float = 30.0,
    ) -> None:
        self._engine = engine
        self._hnsw_path = resolve_semantic_namespace_path(engine, preferred_path=hnsw_path)
        self._writer_embedder = LocalSemanticEmbedder(model_path=None)
        self._hnsw = (
            HnswManager(
                self._hnsw_path,
                dim=self._writer_embedder.dim,
                namespace_path=self._hnsw_path,
            )
            if self._hnsw_path is not None
            else None
        )
        self._generation_lifecycle = (
            _GenerationLifecycleCoordinator(
                engine,
                self._hnsw,
                idle_poll_seconds=generation_gc_idle_poll_seconds,
            )
            if enable_generation_gc_owner and self._hnsw is not None
            else None
        )
        if self._generation_lifecycle is not None:
            self._generation_lifecycle.start()

    @property
    def embedder(self) -> LocalSemanticEmbedder:
        return self._writer_embedder

    @property
    def hnsw_manager(self) -> HnswManager | None:
        return self._hnsw

    @property
    def hnsw_path(self) -> Path | None:
        return self._hnsw_path

    def ensure_ready(self) -> None:
        """Repair or initialize the dense artifact if a manager is configured."""
        if self._hnsw is None:
            return
        self._hnsw.check_and_repair(self._engine, embedder=self._writer_embedder)

    def compensate_if_dirty(self, *, reason: str) -> str:
        """Rebuild the artifact only when the dirty flag is present."""
        if self._hnsw is None:
            return "unconfigured"
        if not self._hnsw.is_dirty():
            return "synced"
        return self.rebuild(reason=reason)

    def rebuild(self, *, reason: str) -> str:
        """Rebuild the dense artifact from SQLite source-of-truth."""
        if self._hnsw is None:
            return "unconfigured"
        try:
            self._hnsw.rebuild_from_db(self._engine, embedder=self._writer_embedder, reason=reason)
        except ArtifactBuildBusyError:
            logger.info("Dense artifact rebuild skipped because another build lease is active")
            return "building"
        except Exception:
            logger.warning("Dense artifact rebuild failed for reason=%s", reason, exc_info=True)
            return "degraded"
        self.request_generation_lifecycle_reconcile()
        return "synced"

    def build_query_backend(self) -> tuple[HnswManager | NullHnswManager, LocalSemanticEmbedder]:
        """Return the currently committed dense bundle for readers."""
        committed_snapshot = self._load_committed_snapshot(reconcile=True)
        if self._hnsw_path is None or committed_snapshot is None:
            return NullHnswManager(self._writer_embedder.dim), LocalSemanticEmbedder(model_path=None)
        if not committed_snapshot.readable or committed_snapshot.bundle_path is None:
            return NullHnswManager(self._writer_embedder.dim), LocalSemanticEmbedder(model_path=None)

        committed_bundle_path = committed_snapshot.bundle_path
        reader_embedder = LocalSemanticEmbedder(
            model_path=committed_bundle_path.with_suffix(".dense_model.npz")
        )
        return (
            HnswManager(
                committed_bundle_path,
                dim=reader_embedder.dim,
                namespace_path=self._hnsw_path,
                allow_create_if_missing=False,
            ),
            reader_embedder,
        )

    def query(self, query: str, *, top_k: int = 5) -> list[SemanticQueryHit]:
        """Run a minimal dense-only query for S3 semantic validation."""
        normalized = query.strip()
        if not normalized:
            raise ValueError("query must not be empty")
        if self._hnsw is None:
            return []
        self.ensure_ready()
        hnsw, embedder = self.build_query_backend()
        vector = embedder.embed_text(normalized)
        return [
            SemanticQueryHit(chunk_id=chunk_id, distance=distance)
            for chunk_id, distance in hnsw.query(vector, k=top_k)
        ]

    def get_artifact_status(self) -> SemanticArtifactStatus:
        """Expose current semantic mode, degradation state, and artifact metadata."""
        committed_snapshot = self._load_committed_snapshot(reconcile=True)
        artifact = self._load_artifact(reconcile=False)

        if self._hnsw is None or artifact is None:
            return SemanticArtifactStatus(
                artifact_name=HnswManager.ARTIFACT_NAME,
                freshness_status="unconfigured",
                semantic_mode=self._writer_embedder.MODEL_NAME,
                degraded=True,
                degraded_reason=_UNCONFIGURED_REASON,
                namespace_path=str(self._hnsw_path) if self._hnsw_path is not None else None,
                committed_artifact_path=None,
                embedder_model=self._writer_embedder.MODEL_NAME,
                embedder_dim=self._writer_embedder.dim,
                embedder_signature=self._writer_embedder.fingerprint,
                generation=0,
                committed_generation=0,
                committed_readable=False,
                committed_readability_reason=_UNCONFIGURED_REASON,
                build_in_progress=False,
                build_started_at=None,
                build_lease_expires_at=None,
                last_error=None,
                last_reason=None,
                last_built_at=None,
                updated_at=None,
            )

        now = utcnow_naive()
        build_in_progress = artifact.active_build_token is not None and (
            artifact.lease_expires_at is None or artifact.lease_expires_at >= now
        )
        committed_readable = committed_snapshot.readable if committed_snapshot is not None else False
        committed_readability_reason = (
            committed_snapshot.readable_reason if committed_snapshot is not None else "committed_bundle_missing"
        )
        degraded_reason = None
        if not committed_readable:
            degraded_reason = committed_readability_reason
        elif artifact.status != "ready":
            degraded_reason = artifact.last_reason
        return SemanticArtifactStatus(
            artifact_name=HnswManager.ARTIFACT_NAME,
            freshness_status=artifact.status,
            semantic_mode=artifact.embedder_model,
            degraded=artifact.status != "ready" or not committed_readable,
            degraded_reason=degraded_reason,
            namespace_path=artifact.namespace_path,
            committed_artifact_path=(
                str(committed_snapshot.bundle_path)
                if committed_snapshot is not None and committed_snapshot.bundle_path is not None
                else None
            ),
            embedder_model=artifact.embedder_model,
            embedder_dim=artifact.embedder_dim,
            embedder_signature=artifact.embedder_signature,
            generation=artifact.generation,
            committed_generation=committed_snapshot.generation if committed_snapshot is not None else 0,
            committed_readable=committed_readable,
            committed_readability_reason=committed_readability_reason,
            build_in_progress=build_in_progress,
            build_started_at=artifact.build_started_at,
            build_lease_expires_at=artifact.lease_expires_at,
            last_error=artifact.last_error,
            last_reason=artifact.last_reason,
            last_built_at=artifact.last_built_at,
            updated_at=artifact.updated_at,
        )

    def _load_artifact(self, *, reconcile: bool) -> object | None:
        if self._hnsw is not None and reconcile:
            self._hnsw.reconcile_public_state(self._engine, embedder=self._writer_embedder)
        with session_scope(self._engine) as session:
            return IndexArtifactRepository(session).get(HnswManager.ARTIFACT_NAME)

    def _load_committed_snapshot(self, *, reconcile: bool) -> CommittedBundleSnapshot | None:
        if self._hnsw is None:
            return None
        return self._hnsw.committed_bundle_snapshot(
            self._engine,
            embedder=self._writer_embedder,
            reconcile=reconcile,
        )

    def request_generation_lifecycle_reconcile(self) -> None:
        if self._generation_lifecycle is not None:
            self._generation_lifecycle.request()

    def tighten_generation_gc_idle_poll_seconds(self, idle_poll_seconds: float) -> None:
        if self._generation_lifecycle is not None:
            self._generation_lifecycle.tighten_idle_poll_seconds(idle_poll_seconds)

    def close(self) -> None:
        if self._generation_lifecycle is not None:
            self._generation_lifecycle.stop()

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            self.close()
        except Exception:
            pass

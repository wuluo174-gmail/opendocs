"""HNSW vector index manager.

S4: upgraded from 64-dim placeholders to 128-dim real embeddings.
HNSW is a *rebuildable derived cache* — SQLite is the source of truth.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import hnswlib
import numpy as np
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opendocs.exceptions import ArtifactBuildBusyError
from opendocs.indexing.dense_artifact_paths import build_dense_model_path
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import IndexArtifactRepository
from opendocs.utils.time import utcnow_naive

logger = logging.getLogger(__name__)

# S4: real embedding dimension (was 64 placeholder in S3).
DEFAULT_DIM = 128
# hnswlib parameters
_EF_CONSTRUCTION = 100
_M = 16
_MAX_ELEMENTS_INIT = 1024
_BUILD_LEASE_TTL = timedelta(minutes=5)
_RETIRED_BUNDLE_RETENTION = timedelta(minutes=10)
_STATE_UNSET = object()
_LEGACY_BUILDING_REASON = "legacy_building_status"


class NullHnswManager:
    """Read-only empty HNSW facade used when no committed dense bundle is available."""

    def __init__(self, dim: int = DEFAULT_DIM) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def query(self, vector: np.ndarray, k: int) -> list[tuple[str, float]]:
        return []

    def query_filtered(
        self,
        vector: np.ndarray,
        *,
        allowed_ids: set[str],
        k: int,
    ) -> list[tuple[str, float]]:
        return []


@dataclass(frozen=True)
class CommittedBundleSnapshot:
    """Resolved committed-generation view used by dense readers."""

    artifact_name: str
    public_status: str
    generation: int
    bundle_path: Path | None
    build_in_progress: bool
    active_build_token: str | None
    build_started_at: datetime | None
    lease_expires_at: datetime | None
    readable: bool
    readable_reason: str | None


class HnswManager:
    """Manage one HNSW bundle plus the shared runtime state for that artifact."""

    ARTIFACT_NAME = "dense_hnsw"

    def __init__(
        self,
        index_path: Path,
        dim: int = DEFAULT_DIM,
        *,
        namespace_path: Path | None = None,
        allow_create_if_missing: bool = True,
    ) -> None:
        self._index_path = Path(index_path).expanduser().resolve()
        self._namespace_path = (
            Path(namespace_path).expanduser().resolve()
            if namespace_path is not None
            else self._index_path
        )
        self._dim = dim
        self._allow_create_if_missing = allow_create_if_missing
        self._lock = threading.RLock()
        self._dirty_path = self._namespace_path.with_suffix(".hnsw_dirty")
        self._labels_path = self._index_path.with_suffix(".hnsw_labels")
        self._vectors_path = self._index_path.with_suffix(".hnsw_vectors.npy")
        self._index: hnswlib.Index | None = None
        self._label_map: dict[str, int] = {}  # chunk_id -> numeric label
        self._next_label: int = 0
        self._deleted_labels: set[int] = set()
        self._vector_store = np.zeros((0, self._dim), dtype=np.float32)

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def index_path(self) -> Path:
        return self._index_path

    @property
    def namespace_path(self) -> Path:
        return self._namespace_path

    def _bundle_root(self) -> Path:
        return self._namespace_path.parent / ".dense_hnsw_bundles"

    def _candidate_index_path(self, build_token: str) -> Path:
        return self._bundle_root() / build_token / self._namespace_path.name

    def _model_path(self) -> Path:
        return build_dense_model_path(self._index_path)

    def _candidate_model_path(self, build_token: str) -> Path:
        return build_dense_model_path(self._candidate_index_path(build_token))

    def ensure_index(self) -> None:
        """Create or load the HNSW index."""
        with self._lock:
            if self._index is not None:
                return
            self._index_path.parent.mkdir(parents=True, exist_ok=True)
            idx = hnswlib.Index(space="cosine", dim=self._dim)
            if self._index_path.exists():
                try:
                    idx.load_index(str(self._index_path))
                    self._load_labels()
                    self._load_vectors()
                except Exception:
                    if not self._allow_create_if_missing:
                        raise
                    logger.warning("HNSW load failed (dimension mismatch?), creating fresh index")
                    idx = hnswlib.Index(space="cosine", dim=self._dim)
                    idx.init_index(
                        max_elements=_MAX_ELEMENTS_INIT,
                        ef_construction=_EF_CONSTRUCTION,
                        M=_M,
                    )
                    self._reset_state()
                    self.mark_dirty()
            else:
                if not self._allow_create_if_missing:
                    raise FileNotFoundError(f"committed HNSW bundle missing: {self._index_path}")
                idx.init_index(
                    max_elements=_MAX_ELEMENTS_INIT,
                    ef_construction=_EF_CONSTRUCTION,
                    M=_M,
                )
                self._reset_state()
            idx.set_ef(50)
            self._index = idx

    def add_chunks(self, chunk_ids: list[str]) -> None:
        """Add zero vectors for chunk_ids (S3 compat / fallback)."""
        if not chunk_ids:
            return
        vectors = np.zeros((len(chunk_ids), self._dim), dtype=np.float32)
        self.add_chunks_with_vectors(chunk_ids, vectors)

    def add_chunks_with_vectors(self, chunk_ids: list[str], vectors: np.ndarray) -> None:
        """Add real vectors for chunk_ids. vectors shape: (N, dim)."""
        if not chunk_ids:
            return
        with self._lock:
            self.ensure_index()
            assert self._index is not None
            vectors = np.asarray(vectors, dtype=np.float32)
            if vectors.ndim != 2 or vectors.shape != (len(chunk_ids), self._dim):
                raise ValueError(
                    "vectors must have shape "
                    f"({len(chunk_ids)}, {self._dim}), got {tuple(vectors.shape)}"
                )

            current_max = self._index.get_max_elements()
            needed = self._next_label + len(chunk_ids)
            if needed > current_max:
                self._index.resize_index(max(needed * 2, current_max * 2))

            labels = []
            for cid in chunk_ids:
                label = self._next_label
                self._next_label += 1
                self._label_map[cid] = label
                labels.append(label)

            self._index.add_items(vectors, labels)
            self._append_vectors(labels, vectors)
            self._save_labels()
            self._save_vectors()
            self._index.save_index(str(self._index_path))

    def query(self, vector: np.ndarray, k: int) -> list[tuple[str, float]]:
        """kNN query. Returns list of (chunk_id, distance)."""
        with self._lock:
            self.ensure_index()
            assert self._index is not None

            if self._index.get_current_count() == 0:
                return []

            reverse_map: dict[int, str] = {v: k_ for k_, v in self._label_map.items()}

            actual_k = min(k, self._index.get_current_count())
            if actual_k == 0:
                return []

            query_vec = vector.reshape(1, -1).astype(np.float32)
            labels_arr, distances_arr = self._index.knn_query(query_vec, k=actual_k)

            results: list[tuple[str, float]] = []
            for label, dist in zip(labels_arr[0], distances_arr[0]):
                label_int = int(label)
                if label_int in self._deleted_labels:
                    continue
                cid = reverse_map.get(label_int)
                if cid is not None:
                    results.append((cid, float(dist)))
                    if len(results) >= k:
                        break
            return results

    def query_filtered(
        self,
        vector: np.ndarray,
        *,
        allowed_ids: set[str],
        k: int,
    ) -> list[tuple[str, float]]:
        """Exact dense scoring on a filtered subset of chunk_ids."""
        if not allowed_ids or k <= 0:
            return []
        with self._lock:
            self.ensure_index()

            candidate_ids: list[str] = []
            candidate_rows: list[int] = []
            for chunk_id in allowed_ids:
                label = self._label_map.get(chunk_id)
                if label is None or label in self._deleted_labels:
                    continue
                if label >= self._vector_store.shape[0]:
                    continue
                candidate_ids.append(chunk_id)
                candidate_rows.append(label)

            if not candidate_rows:
                return []

            query_vec = np.asarray(vector, dtype=np.float32).reshape(-1)
            norm = np.linalg.norm(query_vec)
            if norm > 0:
                query_vec = query_vec / norm

            candidate_vectors = self._vector_store[candidate_rows]
            distances = 1.0 - np.matmul(candidate_vectors, query_vec)
            top_indices = self._top_k_distance_indices(distances, k)
            return [(candidate_ids[idx], float(distances[idx])) for idx in top_indices]

    def mark_deleted(self, chunk_ids: list[str]) -> None:
        """Mark chunks as deleted (filter from results, cleaned up on rebuild)."""
        with self._lock:
            for cid in chunk_ids:
                label = self._label_map.pop(cid, None)
                if label is not None:
                    self._deleted_labels.add(label)
            self._save_labels()

    def mark_dirty(self) -> None:
        with self._lock:
            self._dirty_path.parent.mkdir(parents=True, exist_ok=True)
            self._dirty_path.write_text("dirty")

    def is_dirty(self) -> bool:
        with self._lock:
            return self._dirty_path.exists()

    def clear_dirty(self) -> None:
        with self._lock:
            if self._dirty_path.exists():
                self._dirty_path.unlink()

    def rebuild_from_db(
        self,
        engine: Engine,
        embedder: object | None = None,
        *,
        reason: str | None = None,
    ) -> None:
        """Rebuild HNSW from all active chunks in the database via immutable bundles."""
        with self._lock:
            rebuild_reason = reason or "rebuild_from_db"
            build_token, previous_bundle_path = self._claim_build(
                engine,
                embedder=embedder,
                reason=rebuild_reason,
            )
            candidate_index_path = self._candidate_index_path(build_token)
            candidate_manager = HnswManager(
                candidate_index_path,
                dim=self._dim,
                namespace_path=self._namespace_path,
            )
            candidate_model_path = self._candidate_model_path(build_token)

            try:
                with Session(engine) as session:
                    rows = session.execute(
                        text(
                            "SELECT c.chunk_id, c.text FROM chunks c "
                            "JOIN documents d ON c.doc_id = d.doc_id "
                            "WHERE d.is_deleted_from_fs = 0"
                        )
                    ).fetchall()
                    chunk_ids = [r[0] for r in rows]
                    chunk_texts = [r[1] for r in rows]

                if embedder is not None and hasattr(embedder, "fit_corpus"):
                    embedder.fit_corpus(chunk_texts)

                candidate_manager.ensure_index()
                if chunk_ids:
                    if embedder is not None and hasattr(embedder, "embed_batch"):
                        vectors = embedder.embed_batch(chunk_texts)
                        candidate_manager.add_chunks_with_vectors(chunk_ids, vectors)
                    else:
                        candidate_manager.add_chunks(chunk_ids)
                else:
                    candidate_manager.save()

                if embedder is not None and hasattr(embedder, "save_model_to"):
                    embedder.save_model_to(candidate_model_path)

                self._assert_bundle_complete(
                    candidate_index_path,
                    require_model=embedder is not None and hasattr(embedder, "save_model_to"),
                )
                completed, retired_bundle_path = self._finish_successful_build(
                    engine,
                    embedder=embedder,
                    build_token=build_token,
                    reason=rebuild_reason,
                    committed_bundle_path=candidate_index_path,
                )
                if not completed:
                    raise ArtifactBuildBusyError(
                        "dense_hnsw build lease was lost before completion"
                    )
            except Exception as exc:
                self.mark_dirty()
                self._finish_failed_build(
                    engine,
                    build_token=build_token,
                    reason=rebuild_reason,
                    last_error=str(exc),
                )
                self._cleanup_bundle_path(candidate_index_path)
                raise

            self.clear_dirty()
            keep_paths = {candidate_index_path}
            if previous_bundle_path is not None:
                keep_paths.add(previous_bundle_path)
            if retired_bundle_path is not None:
                keep_paths.add(retired_bundle_path)
            self._prune_bundle_store(engine, keep_paths=keep_paths)
            self._reload_live_bundle()
            logger.info("HNSW rebuilt from DB with %d chunks", len(chunk_ids))

    def save(self) -> None:
        with self._lock:
            if self._index is not None:
                self._index.save_index(str(self._index_path))
                self._save_labels()
                self._save_vectors()

    def check_and_repair(self, engine: Engine, embedder: object | None = None) -> None:
        """On startup: repair dirty, incompatible, or stale HNSW state."""
        with self._lock:
            self._reconcile_generation_lifecycle_locked(engine)
            state = self._load_or_init_artifact_state(engine, embedder=embedder)
            reason = self._rebuild_reason(engine, state)
            if reason == "build_lease_expired":
                self.reconcile_public_state(engine, embedder=embedder)
                state = self._load_or_init_artifact_state(engine, embedder=embedder)
                reason = self._rebuild_reason(engine, state)
            elif reason == "artifact_build_in_progress" and state.status == "building":
                self.reconcile_public_state(engine, embedder=embedder)
                return

            if reason in {None, "artifact_build_in_progress"}:
                return

            logger.warning("HNSW dirty/incompatible state detected, rebuilding from DB: %s", reason)
            self.mark_dirty()
            self._write_artifact_state(
                engine,
                status="stale",
                reason=reason,
                last_error=None,
            )
            self.rebuild_from_db(engine, embedder=embedder, reason=reason)

    def mark_stale(
        self,
        session: Session,
        *,
        embedder: object | None = None,
        reason: str,
        last_error: str | None = None,
    ) -> None:
        self._write_artifact_state_session(
            session,
            status="stale",
            reason=reason,
            last_error=last_error,
            embedder=embedder,
        )

    def mark_ready(
        self,
        engine: Engine,
        *,
        embedder: object | None = None,
        reason: str,
    ) -> None:
        self._write_artifact_state(
            engine,
            status="ready",
            reason=reason,
            active_build_token=None,
            build_started_at=None,
            lease_expires_at=None,
            last_error=None,
            last_built_at=utcnow_naive(),
            embedder=embedder,
        )

    def mark_failed(
        self,
        engine: Engine,
        *,
        embedder: object | None = None,
        reason: str,
        last_error: str,
    ) -> None:
        self._write_artifact_state(
            engine,
            status="failed",
            reason=reason,
            active_build_token=None,
            build_started_at=None,
            lease_expires_at=None,
            last_error=last_error,
            embedder=embedder,
        )

    def reconcile_public_state(self, engine: Engine, *, embedder: object | None = None) -> None:
        """Collapse runtime drift back into the persisted public artifact state."""
        with self._lock:
            self._reconcile_generation_lifecycle_locked(engine)
            state = self._load_or_init_artifact_state(engine, embedder=embedder)
            reason = self._rebuild_reason(engine, state)
            if reason is None:
                return
            if reason == "artifact_build_in_progress" and state.status != "building":
                return
            if reason == "build_lease_expired":
                with session_scope(engine) as session:
                    repo = IndexArtifactRepository(session)
                    repo.expire_build_lease(
                        self.ARTIFACT_NAME,
                        expired_before=utcnow_naive(),
                        reason=reason,
                    )
                return

            status_echo_reason = f"artifact_status:{state.status}"
            canonical_status = self._canonical_public_status(state, reason=reason)
            if (
                state.status == canonical_status
                and (
                    state.last_reason == reason
                    or (
                        state.status in {"stale", "failed"}
                        and reason == status_echo_reason
                        and state.last_reason is not None
                    )
                )
            ):
                return

            persisted_reason = reason
            if state.status in {"stale", "failed"} and reason == status_echo_reason:
                persisted_reason = state.last_reason or reason
            elif state.status == "building":
                persisted_reason = state.last_reason or _LEGACY_BUILDING_REASON

            kwargs: dict[str, object] = {}
            if state.status in {"ready", "building"} and canonical_status == "stale":
                kwargs["last_error"] = None
            self._write_artifact_state(
                engine,
                status=canonical_status,
                active_build_token=state.active_build_token,
                build_started_at=state.build_started_at,
                lease_expires_at=state.lease_expires_at,
                reason=persisted_reason,
                **kwargs,
            )

    def committed_bundle_snapshot(
        self,
        engine: Engine,
        *,
        embedder: object | None = None,
        reconcile: bool = True,
    ) -> CommittedBundleSnapshot:
        """Resolve the currently committed generation independent of freshness status."""
        with self._lock:
            if reconcile:
                self.reconcile_public_state(engine, embedder=embedder)
            state = self._load_or_init_artifact_state(engine, embedder=embedder)
            committed_generation = self._committed_generation_row(engine, state)
            now = utcnow_naive()
            build_in_progress = state.active_build_token is not None and (
                state.lease_expires_at is None or state.lease_expires_at >= now
            )
            readable_reason = self._committed_reader_reason(engine, state)
            return CommittedBundleSnapshot(
                artifact_name=self.ARTIFACT_NAME,
                public_status=state.status,
                generation=committed_generation.generation if committed_generation is not None else 0,
                bundle_path=self._committed_bundle_path(engine, state),
                build_in_progress=build_in_progress,
                active_build_token=state.active_build_token,
                build_started_at=state.build_started_at,
                lease_expires_at=state.lease_expires_at,
                readable=readable_reason is None,
                readable_reason=readable_reason,
            )

    def reconcile_generation_lifecycle(self, engine: Engine) -> None:
        """Consume due retained-generation lifecycle transitions independently of rebuild."""
        with self._lock:
            self._reconcile_generation_lifecycle_locked(engine)

    def next_generation_gc_deadline(self, engine: Engine) -> datetime | None:
        """Return the next retained-generation GC deadline for the current artifact."""
        with self._lock:
            with session_scope(engine) as session:
                return IndexArtifactRepository(session).next_gc_due_at(self.ARTIFACT_NAME)

    def _claim_build(
        self,
        engine: Engine,
        *,
        embedder: object | None,
        reason: str,
    ) -> tuple[str, Path | None]:
        model_name, dim, signature = self._artifact_profile(embedder)
        build_token = str(uuid.uuid4())
        now = utcnow_naive()
        lease_expires_at = now + _BUILD_LEASE_TTL
        with session_scope(engine) as session:
            repo = IndexArtifactRepository(session)
            artifact = repo.ensure_artifact(
                self.ARTIFACT_NAME,
                namespace_path=str(self._namespace_path),
                embedder_model=model_name,
                embedder_dim=dim,
                embedder_signature=signature,
            )
            current_generation = (
                repo.get_generation(self.ARTIFACT_NAME, artifact.generation)
                if artifact.generation > 0
                else None
            )
            if current_generation is None and artifact.generation > 0:
                current_generation = repo.get_committed_generation(self.ARTIFACT_NAME)
            previous_bundle_path = (
                Path(current_generation.bundle_path).expanduser().resolve()
                if current_generation is not None
                else None
            )
            claimed = repo.try_claim_build(
                self.ARTIFACT_NAME,
                namespace_path=str(self._namespace_path),
                embedder_model=model_name,
                embedder_dim=dim,
                embedder_signature=signature,
                build_token=build_token,
                build_started_at=now,
                lease_expires_at=lease_expires_at,
                reason=reason,
            )
        if not claimed:
            raise ArtifactBuildBusyError("dense_hnsw build is already in progress")
        return build_token, previous_bundle_path

    def _finish_successful_build(
        self,
        engine: Engine,
        *,
        embedder: object | None,
        build_token: str,
        reason: str,
        committed_bundle_path: Path,
    ) -> tuple[bool, Path | None]:
        model_name, dim, signature = self._artifact_profile(embedder)
        with session_scope(engine) as session:
            repo = IndexArtifactRepository(session)
            completed, previous_bundle_path = repo.complete_build(
                self.ARTIFACT_NAME,
                build_token=build_token,
                reason=reason,
                last_built_at=utcnow_naive(),
                committed_bundle_path=str(committed_bundle_path),
                embedder_model=model_name,
                embedder_dim=dim,
                embedder_signature=signature,
                retained_delete_after=utcnow_naive() + _RETIRED_BUNDLE_RETENTION,
            )
        return (
            completed,
            Path(previous_bundle_path).expanduser().resolve()
            if completed and previous_bundle_path is not None
            else None,
        )

    def _finish_failed_build(
        self,
        engine: Engine,
        *,
        build_token: str,
        reason: str,
        last_error: str | None,
    ) -> None:
        with session_scope(engine) as session:
            repo = IndexArtifactRepository(session)
            repo.fail_build(
                self.ARTIFACT_NAME,
                build_token=build_token,
                status="failed",
                reason=reason,
                last_error=last_error,
            )

    def _prune_bundle_store(self, engine: Engine, *, keep_paths: set[Path]) -> None:
        bundle_root = self._bundle_root()
        if not bundle_root.exists():
            return

        active_build_token: str | None = None
        live_bundle_paths: set[Path] = set()
        with session_scope(engine) as session:
            repo = IndexArtifactRepository(session)
            state = repo.get(self.ARTIFACT_NAME)
            if state is not None:
                active_build_token = state.active_build_token
                gc_due = repo.list_gc_due_generations(
                    self.ARTIFACT_NAME,
                    delete_before=utcnow_naive(),
                )
                gc_due_keys = {generation_row.generation for generation_row in gc_due}
                for generation_row in repo.list_generations(self.ARTIFACT_NAME):
                    if generation_row.generation in gc_due_keys:
                        continue
                    live_bundle_paths.add(Path(generation_row.bundle_path).expanduser().resolve())
                for generation_row in gc_due:
                    bundle_path = Path(generation_row.bundle_path).expanduser().resolve()
                    if bundle_path in keep_paths:
                        continue
                    self._cleanup_bundle_path(bundle_path)
                    repo.mark_generation_deleted(
                        self.ARTIFACT_NAME,
                        generation=generation_row.generation,
                        deleted_at=utcnow_naive(),
                    )

        keep_dirs = {path.parent.resolve() for path in keep_paths}
        keep_dirs.update(path.parent.resolve() for path in live_bundle_paths)
        if active_build_token is not None:
            keep_dirs.add((bundle_root / active_build_token).resolve())
        retained_after_epoch = utcnow_naive().timestamp() - _RETIRED_BUNDLE_RETENTION.total_seconds()

        for candidate_dir in bundle_root.iterdir():
            if not candidate_dir.is_dir():
                continue
            resolved_dir = candidate_dir.resolve()
            if resolved_dir in keep_dirs:
                continue
            try:
                if candidate_dir.stat().st_mtime >= retained_after_epoch:
                    continue
            except FileNotFoundError:
                continue
            shutil.rmtree(candidate_dir, ignore_errors=True)

    def _cleanup_bundle_path(
        self,
        bundle_path: Path | None,
        *,
        keep_paths: set[Path] | None = None,
    ) -> None:
        if bundle_path is None:
            return
        resolved_bundle_path = bundle_path.expanduser().resolve()
        if keep_paths and resolved_bundle_path in {path.expanduser().resolve() for path in keep_paths}:
            return
        if resolved_bundle_path == self._namespace_path:
            for sidecar_path in self._bundle_sidecars(resolved_bundle_path):
                if sidecar_path.exists():
                    sidecar_path.unlink()
            return
        bundle_root = self._bundle_root().resolve()
        try:
            resolved_bundle_path.relative_to(bundle_root)
        except ValueError:
            return
        candidate_dir = resolved_bundle_path.parent
        if candidate_dir.exists():
            shutil.rmtree(candidate_dir, ignore_errors=True)

    def _reload_live_bundle(self) -> None:
        self._index = None
        self._reset_state()

    def _save_labels(self) -> None:
        data = {
            "dim": self._dim,
            "label_map": self._label_map,
            "next_label": self._next_label,
            "deleted_labels": list(self._deleted_labels),
        }
        self._labels_path.write_text(json.dumps(data))

    def _save_vectors(self) -> None:
        np.save(self._vectors_path, self._vector_store)

    def _load_labels(self) -> None:
        if not self._labels_path.exists():
            raise ValueError("HNSW labels metadata missing")
        data = json.loads(self._labels_path.read_text())
        stored_dim = data.get("dim")
        if stored_dim != self._dim:
            raise ValueError(f"HNSW dim metadata mismatch: expected {self._dim}, got {stored_dim}")
        self._label_map = data.get("label_map", {})
        self._next_label = data.get("next_label", 0)
        self._deleted_labels = set(data.get("deleted_labels", []))

    def _load_vectors(self) -> None:
        if not self._vectors_path.exists():
            raise ValueError("HNSW vector metadata missing")
        vectors = np.load(self._vectors_path, allow_pickle=False)
        if vectors.ndim != 2 or vectors.shape[1] != self._dim:
            raise ValueError(
                f"HNSW vector metadata shape mismatch: expected (*, {self._dim}), "
                f"got {tuple(vectors.shape)}"
            )
        if vectors.shape[0] != self._next_label:
            raise ValueError(
                "HNSW vector metadata row count mismatch: "
                f"expected {self._next_label}, got {vectors.shape[0]}"
            )
        self._vector_store = np.asarray(vectors, dtype=np.float32)

    def _append_vectors(self, labels: list[int], vectors: np.ndarray) -> None:
        if not labels:
            return
        if self._vector_store.shape[0] < self._next_label:
            padding = np.zeros(
                (self._next_label - self._vector_store.shape[0], self._dim),
                dtype=np.float32,
            )
            self._vector_store = np.vstack([self._vector_store, padding])
        self._vector_store[np.asarray(labels, dtype=np.int64)] = vectors

    @staticmethod
    def _top_k_distance_indices(distances: np.ndarray, k: int) -> np.ndarray:
        limit = min(k, len(distances))
        if limit <= 0:
            return np.asarray([], dtype=np.int64)
        if len(distances) <= limit:
            return np.argsort(distances, kind="stable")
        top = np.argpartition(distances, limit - 1)[:limit]
        return top[np.argsort(distances[top], kind="stable")]

    def _reset_state(self) -> None:
        self._label_map = {}
        self._next_label = 0
        self._deleted_labels = set()
        self._vector_store = np.zeros((0, self._dim), dtype=np.float32)

    def _artifact_profile(self, embedder: object | None) -> tuple[str, int, str]:
        model_name = "unknown"
        signature = f"unknown|dim={self._dim}"
        if embedder is not None:
            model_name = getattr(embedder, "MODEL_NAME", embedder.__class__.__name__)
            signature = getattr(embedder, "fingerprint", signature)
        return model_name, self._dim, signature

    def _load_or_init_artifact_state(self, engine: Engine, embedder: object | None):
        model_name, dim, signature = self._artifact_profile(embedder)
        with session_scope(engine) as session:
            repo = IndexArtifactRepository(session)
            artifact = repo.ensure_artifact(
                self.ARTIFACT_NAME,
                namespace_path=str(self._namespace_path),
                embedder_model=model_name,
                embedder_dim=dim,
                embedder_signature=signature,
            )
            return artifact

    def _reconcile_generation_lifecycle_locked(self, engine: Engine) -> None:
        self._prune_bundle_store(engine, keep_paths=set())

    def _rebuild_reason(self, engine: Engine, state) -> str | None:
        now = utcnow_naive()
        if state.active_build_token is not None:
            if state.lease_expires_at is None or state.lease_expires_at < now:
                return "build_lease_expired"
            if (
                state.status == "ready"
                and self._committed_reader_reason(engine, state) is None
                and not self.is_dirty()
            ):
                return None
            return "artifact_build_in_progress"
        if state.status == "building":
            return _LEGACY_BUILDING_REASON
        if state.status != "ready":
            return f"artifact_status:{state.status}"
        committed_reader_reason = self._committed_reader_reason(engine, state)
        if committed_reader_reason is not None:
            return committed_reader_reason
        if self.is_dirty():
            return "dirty_flag_present"
        return None

    @staticmethod
    def _canonical_public_status(state, *, reason: str) -> str:
        if state.status in {"stale", "failed"}:
            return state.status
        if state.status == "building":
            return "stale"
        if state.status == "ready":
            return "stale" if reason is not None else "ready"
        return "stale"

    def _committed_generation_row(self, engine: Engine, state):
        if state.generation <= 0:
            return None
        with session_scope(engine) as session:
            repo = IndexArtifactRepository(session)
            generation_row = repo.get_generation(self.ARTIFACT_NAME, state.generation)
            if generation_row is None:
                generation_row = repo.get_committed_generation(self.ARTIFACT_NAME)
            return generation_row

    def _committed_bundle_path(self, engine: Engine, state) -> Path | None:
        generation_row = self._committed_generation_row(engine, state)
        if generation_row is None:
            return None
        return Path(generation_row.bundle_path).expanduser().resolve()

    def _committed_bundle_reason(self, engine: Engine, state) -> str | None:
        namespace_path = Path(state.namespace_path).expanduser().resolve()
        if namespace_path != self._namespace_path:
            return "namespace_path_changed"
        generation_row = self._committed_generation_row(engine, state)
        if generation_row is None:
            return "committed_bundle_missing"
        if generation_row.generation != state.generation:
            return "committed_generation_mismatch"
        committed_bundle_path = self._committed_bundle_path(engine, state)
        if committed_bundle_path is None:
            return "committed_bundle_missing"
        if not self._is_namespace_managed_path(committed_bundle_path):
            return "committed_bundle_unmanaged"
        if not committed_bundle_path.exists():
            return "index_file_missing"
        if not committed_bundle_path.with_suffix(".hnsw_labels").exists():
            return "labels_file_missing"
        if not committed_bundle_path.with_suffix(".hnsw_vectors.npy").exists():
            return "vectors_file_missing"
        if not build_dense_model_path(committed_bundle_path).exists():
            return "model_file_missing"
        return None

    def _is_namespace_managed_path(self, index_path: Path) -> bool:
        resolved_index_path = index_path.expanduser().resolve()
        if resolved_index_path == self._namespace_path:
            return True
        try:
            resolved_index_path.relative_to(self._bundle_root().resolve())
        except ValueError:
            return False
        return True

    def _committed_bundle_profile(self, engine: Engine, state) -> tuple[str, int, str] | None:
        committed_bundle_path = self._committed_bundle_path(engine, state)
        if committed_bundle_path is None:
            return None
        model_path = build_dense_model_path(committed_bundle_path)
        if not model_path.exists():
            return None
        from opendocs.retrieval.embedder import LocalSemanticEmbedder

        embedder = LocalSemanticEmbedder(model_path=model_path)
        return (embedder.MODEL_NAME, embedder.dim, embedder.fingerprint)

    def _committed_reader_reason(self, engine: Engine, state) -> str | None:
        committed_bundle_reason = self._committed_bundle_reason(engine, state)
        if committed_bundle_reason is not None:
            return committed_bundle_reason
        try:
            committed_profile = self._committed_bundle_profile(engine, state)
        except Exception as exc:
            return f"embedder_profile_invalid:{exc.__class__.__name__}"
        if committed_profile is not None:
            if state.embedder_model != committed_profile[0]:
                return "embedder_model_changed"
            if state.embedder_dim != committed_profile[1]:
                return "embedder_dim_changed"
            if state.embedder_signature != committed_profile[2]:
                return "embedder_signature_changed"
        return None

    def _bundle_sidecars(self, index_path: Path) -> tuple[Path, Path, Path, Path]:
        resolved_index_path = index_path.expanduser().resolve()
        return (
            resolved_index_path,
            resolved_index_path.with_suffix(".hnsw_labels"),
            resolved_index_path.with_suffix(".hnsw_vectors.npy"),
            build_dense_model_path(resolved_index_path),
        )

    def _assert_bundle_complete(self, index_path: Path, *, require_model: bool) -> None:
        required_paths = list(self._bundle_sidecars(index_path)[:3])
        if require_model:
            required_paths.append(self._bundle_sidecars(index_path)[3])
        for required_path in required_paths:
            if not required_path.exists():
                raise FileNotFoundError(f"bundle artifact missing: {required_path}")

    def _write_artifact_state(
        self,
        engine: Engine,
        *,
        status: str,
        generation: int | object = _STATE_UNSET,
        active_build_token: str | None | object = _STATE_UNSET,
        build_started_at: object = _STATE_UNSET,
        lease_expires_at: object = _STATE_UNSET,
        reason: str | None | object = _STATE_UNSET,
        last_error: str | None | object = _STATE_UNSET,
        last_built_at: object = _STATE_UNSET,
        namespace_path: str | Path | object = _STATE_UNSET,
        persist_profile: bool = False,
        embedder: object | None = None,
    ) -> None:
        with session_scope(engine) as session:
            self._write_artifact_state_session(
                session,
                status=status,
                generation=generation,
                active_build_token=active_build_token,
                build_started_at=build_started_at,
                lease_expires_at=lease_expires_at,
                reason=reason,
                last_error=last_error,
                last_built_at=last_built_at,
                namespace_path=namespace_path,
                persist_profile=persist_profile,
                embedder=embedder,
            )

    def _write_artifact_state_session(
        self,
        session: Session,
        *,
        status: str,
        generation: int | object = _STATE_UNSET,
        active_build_token: str | None | object = _STATE_UNSET,
        build_started_at: object = _STATE_UNSET,
        lease_expires_at: object = _STATE_UNSET,
        reason: str | None | object = _STATE_UNSET,
        last_error: str | None | object = _STATE_UNSET,
        last_built_at: object = _STATE_UNSET,
        namespace_path: str | Path | object = _STATE_UNSET,
        persist_profile: bool = False,
        embedder: object | None = None,
    ) -> None:
        repo = IndexArtifactRepository(session)
        existing_artifact = repo.get(self.ARTIFACT_NAME)
        kwargs: dict[str, object] = {}
        if namespace_path is not _STATE_UNSET:
            kwargs["namespace_path"] = str(Path(namespace_path).expanduser().resolve())
        if persist_profile:
            model_name, dim, signature = self._artifact_profile(embedder)
            kwargs["embedder_model"] = model_name
            kwargs["embedder_dim"] = dim
            kwargs["embedder_signature"] = signature
        if existing_artifact is None:
            kwargs.setdefault("namespace_path", str(self._namespace_path))
            if "embedder_model" not in kwargs:
                model_name, dim, signature = self._artifact_profile(embedder)
                kwargs["embedder_model"] = model_name
                kwargs["embedder_dim"] = dim
                kwargs["embedder_signature"] = signature
        if generation is not _STATE_UNSET:
            kwargs["generation"] = generation
        if active_build_token is not _STATE_UNSET:
            kwargs["active_build_token"] = active_build_token
        if build_started_at is not _STATE_UNSET:
            kwargs["build_started_at"] = build_started_at
        if lease_expires_at is not _STATE_UNSET:
            kwargs["lease_expires_at"] = lease_expires_at
        if reason is not _STATE_UNSET:
            kwargs["last_reason"] = reason
        if last_error is not _STATE_UNSET:
            kwargs["last_error"] = last_error
        if last_built_at is not _STATE_UNSET:
            kwargs["last_built_at"] = last_built_at
        repo.upsert(
            self.ARTIFACT_NAME,
            status=status,
            **kwargs,
        )

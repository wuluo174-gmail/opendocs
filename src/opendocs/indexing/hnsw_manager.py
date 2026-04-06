"""HNSW vector index manager.

S4: upgraded from 64-dim placeholders to 128-dim real embeddings.
HNSW is a *rebuildable derived cache* — SQLite is the source of truth.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

import hnswlib
import numpy as np
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

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
_STATE_UNSET = object()


class HnswManager:
    """Manage an hnswlib index file with dirty-flag recovery."""

    ARTIFACT_NAME = "dense_hnsw"

    def __init__(self, index_path: Path, dim: int = DEFAULT_DIM) -> None:
        self._index_path = Path(index_path)
        self._dim = dim
        self._lock = threading.RLock()
        self._dirty_path = self._index_path.with_suffix(".hnsw_dirty")
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
                    # Dimension mismatch or corruption → fresh index
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

            # Build reverse map: label -> chunk_id
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
        """Exact dense scoring on a filtered subset of chunk_ids.

        HNSW remains the ANN path for unfiltered search. Once filters narrow the
        search space, exact scoring on the derived vector sidecar is both simpler
        and avoids accidental whole-index scans.
        """
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
        """Rebuild HNSW from all active chunks in the database.

        If embedder is provided, computes real vectors from chunk text.
        Otherwise falls back to zero vectors.
        """
        with self._lock:
            rebuild_reason = reason or "rebuild_from_db"
            self._write_artifact_state(
                engine,
                status="building",
                embedder=embedder,
                reason=rebuild_reason,
                last_error=None,
            )

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

                # Reset and rebuild
                self._index = None
                self._reset_state()

                idx = hnswlib.Index(space="cosine", dim=self._dim)
                max_elements = max(len(chunk_ids), _MAX_ELEMENTS_INIT)
                idx.init_index(
                    max_elements=max_elements,
                    ef_construction=_EF_CONSTRUCTION,
                    M=_M,
                )
                idx.set_ef(50)
                self._index = idx

                if chunk_ids:
                    if embedder is not None and hasattr(embedder, "embed_batch"):
                        vectors = embedder.embed_batch(chunk_texts)
                        self.add_chunks_with_vectors(chunk_ids, vectors)
                    else:
                        self.add_chunks(chunk_ids)
            except Exception as exc:
                self.mark_dirty()
                self._write_artifact_state(
                    engine,
                    status="failed",
                    embedder=embedder,
                    reason=rebuild_reason,
                    last_error=str(exc),
                )
                raise

            self.clear_dirty()
            self._write_artifact_state(
                engine,
                status="ready",
                embedder=embedder,
                reason=rebuild_reason,
                last_error=None,
                last_built_at=utcnow_naive(),
            )
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
            state = self._load_or_init_artifact_state(engine, embedder=embedder)
            reason = self._rebuild_reason(state, embedder=embedder)

            if reason is None:
                try:
                    self.ensure_index()
                except Exception as exc:
                    reason = f"health_check_exception:{exc.__class__.__name__}"
                else:
                    if self.is_dirty():
                        reason = "health_check_marked_dirty"

            if reason is None:
                return

            logger.warning("HNSW dirty/incompatible state detected, rebuilding from DB: %s", reason)
            self.mark_dirty()
            self._write_artifact_state(
                engine,
                status="stale",
                embedder=embedder,
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
            embedder=embedder,
            reason=reason,
            last_error=last_error,
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
            embedder=embedder,
            reason=reason,
            last_error=None,
            last_built_at=utcnow_naive(),
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
            embedder=embedder,
            reason=reason,
            last_error=last_error,
        )

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
        with session_scope(engine) as session:
            repo = IndexArtifactRepository(session)
            state = repo.get(self.ARTIFACT_NAME)
            if state is None:
                self._write_artifact_state_session(
                    session,
                    status="stale",
                    embedder=embedder,
                    reason="artifact_record_created",
                    last_error=None,
                )
                state = repo.get(self.ARTIFACT_NAME)
            assert state is not None
            return state

    def _rebuild_reason(self, state, *, embedder: object | None) -> str | None:
        model_name, dim, signature = self._artifact_profile(embedder)
        if state.status != "ready":
            return f"artifact_status:{state.status}"
        if state.artifact_path != str(self._index_path):
            return "artifact_path_changed"
        if state.embedder_model != model_name:
            return "embedder_model_changed"
        if state.embedder_dim != dim:
            return "embedder_dim_changed"
        if state.embedder_signature != signature:
            return "embedder_signature_changed"
        if self.is_dirty():
            return "dirty_flag_present"
        if not self._index_path.exists():
            return "index_file_missing"
        if not self._labels_path.exists():
            return "labels_file_missing"
        if not self._vectors_path.exists():
            return "vectors_file_missing"
        return None

    def _write_artifact_state(
        self,
        engine: Engine,
        *,
        status: str,
        embedder: object | None,
        reason: str | None | object = _STATE_UNSET,
        last_error: str | None | object = _STATE_UNSET,
        last_built_at: object = _STATE_UNSET,
    ) -> None:
        with session_scope(engine) as session:
            self._write_artifact_state_session(
                session,
                status=status,
                embedder=embedder,
                reason=reason,
                last_error=last_error,
                last_built_at=last_built_at,
            )

    def _write_artifact_state_session(
        self,
        session: Session,
        *,
        status: str,
        embedder: object | None,
        reason: str | None | object = _STATE_UNSET,
        last_error: str | None | object = _STATE_UNSET,
        last_built_at: object = _STATE_UNSET,
    ) -> None:
        repo = IndexArtifactRepository(session)
        model_name, dim, signature = self._artifact_profile(embedder)
        kwargs: dict[str, object] = {}
        if reason is not _STATE_UNSET:
            kwargs["last_reason"] = reason
        if last_error is not _STATE_UNSET:
            kwargs["last_error"] = last_error
        if last_built_at is not _STATE_UNSET:
            kwargs["last_built_at"] = last_built_at
        repo.upsert(
            self.ARTIFACT_NAME,
            status=status,
            artifact_path=str(self._index_path),
            embedder_model=model_name,
            embedder_dim=dim,
            embedder_signature=signature,
            **kwargs,
        )

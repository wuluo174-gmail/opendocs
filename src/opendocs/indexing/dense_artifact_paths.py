"""Path helpers for dense semantic sidecar artifacts."""

from __future__ import annotations

from pathlib import Path

_MODEL_FILE_SUFFIX = ".dense_model.npz"


def build_dense_model_path(index_path: str | Path) -> Path:
    """Return the semantic-model artifact path for one HNSW index."""
    return Path(index_path).with_suffix(_MODEL_FILE_SUFFIX)

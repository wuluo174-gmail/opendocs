"""Dense vector search via HNSW."""

from __future__ import annotations

from opendocs.indexing.hnsw_manager import HnswManager
from opendocs.retrieval.embedder import LocalNgramEmbedder


class DenseSearcher:
    """Embed a query and search the HNSW index."""

    def __init__(self, hnsw: HnswManager, embedder: LocalNgramEmbedder) -> None:
        self._hnsw = hnsw
        self._embedder = embedder

    def search(
        self,
        query: str,
        k: int = 36,
        allowed_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        """Return list of (chunk_id, cosine_distance). Lower distance = more similar."""
        vec = self._embedder.embed_text(query)
        return self._hnsw.query(vec, k=k, allowed_ids=allowed_ids)

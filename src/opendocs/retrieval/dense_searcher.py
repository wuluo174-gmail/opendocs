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
    ) -> list[tuple[str, float]]:
        """Return list of (chunk_id, cosine_distance). Lower distance = more similar."""
        vec = self._embedder.embed_text(query)
        return self._hnsw.query(vec, k=k)

    def search_filtered(
        self,
        query: str,
        *,
        allowed_ids: set[str],
        k: int = 36,
    ) -> list[tuple[str, float]]:
        """Return exact dense scores for a filtered candidate subset."""
        vec = self._embedder.embed_text(query)
        return self._hnsw.query_filtered(vec, allowed_ids=allowed_ids, k=k)

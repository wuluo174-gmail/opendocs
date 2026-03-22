"""Local n-gram hash embedder for dense retrieval.

Produces 128-dim vectors from character n-grams. Zero external dependencies
beyond numpy (already available via hnswlib). Deterministic and fully offline.
"""

from __future__ import annotations

import hashlib

import numpy as np


def _is_cjk(ch: str) -> bool:
    """Check if a character is CJK. Ranges mirror chunker.py:28-33."""
    cp = ord(ch)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0xF900 <= cp <= 0xFAFF
        or 0x20000 <= cp <= 0x2FA1F
    )


class LocalNgramEmbedder:
    """Character n-gram hash vectorizer.

    CJK: unigram + bigram. Latin: bigram + trigram.
    Hashes into fixed-dim buckets, L2-normalized.
    """

    MODEL_NAME = "local-ngram-hash-v1"
    MODEL_FINGERPRINT = "local-ngram-hash-v1|cjk=1,2|latin=2,3|hash=md5|norm=l2"
    DIM = 128

    def __init__(self, dim: int | None = None) -> None:
        self._dim = dim or self.DIM

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def fingerprint(self) -> str:
        return f"{self.MODEL_FINGERPRINT}|dim={self._dim}"

    def embed_text(self, text: str) -> np.ndarray:
        """Embed a single text string. Returns (dim,) float32, L2-normalized."""
        vec = np.zeros(self._dim, dtype=np.float32)
        if not text or not text.strip():
            return vec

        ngrams = self._extract_ngrams(text)
        for ng in ngrams:
            bucket = self._hash_to_bucket(ng)
            vec[bucket] += 1.0

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Embed multiple texts. Returns (N, dim) float32."""
        return np.array([self.embed_text(t) for t in texts], dtype=np.float32)

    def _extract_ngrams(self, text: str) -> list[str]:
        """Extract character n-grams from text."""
        ngrams: list[str] = []
        chars = list(text)
        n = len(chars)
        for i, ch in enumerate(chars):
            if _is_cjk(ch):
                # CJK: unigram + bigram
                ngrams.append(ch)
                if i + 1 < n:
                    ngrams.append(ch + chars[i + 1])
            else:
                # Latin/other: bigram + trigram
                if i + 1 < n:
                    ngrams.append(ch + chars[i + 1])
                if i + 2 < n:
                    ngrams.append(ch + chars[i + 1] + chars[i + 2])
        return ngrams

    def _hash_to_bucket(self, ngram: str) -> int:
        """Hash an n-gram to a bucket index in [0, dim)."""
        h = hashlib.md5(ngram.encode("utf-8"), usedforsecurity=False).digest()
        return int.from_bytes(h[:4], "little") % self._dim

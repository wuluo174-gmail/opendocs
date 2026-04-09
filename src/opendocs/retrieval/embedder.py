"""Local corpus-trained semantic embedder for dense retrieval.

The dense channel is a derived artifact owned by the indexed corpus itself:
1. tokenize active chunk texts + runtime-owned synonym concepts
2. build a TF-IDF matrix
3. learn a low-rank latent projection (LSA)
4. persist the projection alongside the HNSW index

This keeps dense retrieval fully offline while making its data owner explicit:
SQLite chunk text is the source of truth, the semantic model is rebuildable.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np

from opendocs.indexing.dense_artifact_paths import build_dense_model_path
from opendocs.parsers.normalization import normalize_text
from opendocs.retrieval.query_lexicon import load_runtime_query_lexicon

_CJK_BLOCK_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[a-z0-9]+")
_SPACE_RE = re.compile(r"\s+")
_MODEL_VERSION = "local-lsa-v1"
_STATE_UNFITTED = "unfitted"
_MAX_VOCAB = 4096


def normalize_embedding_text(text: str) -> str:
    """Canonicalize dense text so queries and indexed chunks share one owner."""
    return _SPACE_RE.sub(" ", normalize_text(text).casefold()).strip()

class LocalSemanticEmbedder:
    """Corpus-trained latent semantic embedder with runtime-owned concept tokens."""

    MODEL_NAME = _MODEL_VERSION
    DIM = 128
    supports_incremental_updates = False

    def __init__(
        self,
        *,
        dim: int | None = None,
        model_path: str | Path | None = None,
    ) -> None:
        self._dim = dim or self.DIM
        self._model_path = Path(model_path) if model_path is not None else None
        self._vocabulary: tuple[str, ...] = ()
        self._vocab_index: dict[str, int] = {}
        self._idf = np.zeros(0, dtype=np.float32)
        self._projection = np.zeros((0, self._dim), dtype=np.float32)
        self._model_hash = _STATE_UNFITTED
        self._lexicon_entries = load_runtime_query_lexicon()
        if self._model_path is not None and self._model_path.exists():
            self.load_model()

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def fingerprint(self) -> str:
        return f"{self.MODEL_NAME}|dim={self._dim}|model={self._model_hash}"

    def fit_corpus(self, texts: list[str]) -> None:
        """Train the semantic model from active chunk texts."""
        tokenized_docs = [self._tokenize_text(text) for text in texts]
        tokenized_docs.extend(self._build_auxiliary_documents())
        vocabulary = self._build_vocabulary(tokenized_docs)

        self._vocabulary = tuple(vocabulary)
        self._vocab_index = {token: idx for idx, token in enumerate(self._vocabulary)}
        if not self._vocabulary:
            self._idf = np.zeros(0, dtype=np.float32)
            self._projection = np.zeros((0, self._dim), dtype=np.float32)
            self._model_hash = self._compute_model_hash()
            return

        matrix = self._build_tfidf_matrix(tokenized_docs)
        projection = self._fit_projection(matrix)
        self._idf = self._compute_idf(tokenized_docs)
        self._projection = projection
        self._model_hash = self._compute_model_hash()

    def embed_text(self, text: str) -> np.ndarray:
        """Embed a single text string. Returns (dim,) float32, L2-normalized."""
        if not self._vocabulary:
            return np.zeros(self._dim, dtype=np.float32)
        vector = self._project_tokens(self._tokenize_text(text))
        return self._normalize_vector(vector)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Embed multiple texts. Returns (N, dim) float32."""
        return np.asarray([self.embed_text(text) for text in texts], dtype=np.float32)

    def save_model(self) -> None:
        """Persist the current semantic model beside the HNSW index."""
        if self._model_path is None:
            return
        self.save_model_to(self._model_path)

    def save_model_to(self, model_path: str | Path) -> None:
        """Persist the current semantic model to one explicit artifact path."""
        resolved_model_path = Path(model_path)
        resolved_model_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            resolved_model_path,
            model_name=np.asarray([self.MODEL_NAME]),
            model_hash=np.asarray([self._model_hash]),
            dim=np.asarray([self._dim], dtype=np.int32),
            vocabulary=np.asarray(self._vocabulary),
            idf=self._idf.astype(np.float32),
            projection=self._projection.astype(np.float32),
        )

    def load_model(self) -> None:
        """Load the persisted semantic model from disk."""
        if self._model_path is None or not self._model_path.exists():
            self._reset_model()
            return
        with np.load(self._model_path, allow_pickle=False) as payload:
            stored_dim = int(payload["dim"][0])
            if stored_dim != self._dim:
                raise ValueError(
                    f"dense model dim mismatch: expected {self._dim}, got {stored_dim}"
                )
            vocabulary = tuple(str(token) for token in payload["vocabulary"].tolist())
            idf = np.asarray(payload["idf"], dtype=np.float32)
            projection = np.asarray(payload["projection"], dtype=np.float32)
            if idf.shape != (len(vocabulary),):
                raise ValueError("dense model idf shape mismatch")
            if projection.shape != (len(vocabulary), self._dim):
                raise ValueError("dense model projection shape mismatch")
            self._vocabulary = vocabulary
            self._vocab_index = {token: idx for idx, token in enumerate(vocabulary)}
            self._idf = idf
            self._projection = projection
            self._model_hash = str(payload["model_hash"][0])

    def _reset_model(self) -> None:
        self._vocabulary = ()
        self._vocab_index = {}
        self._idf = np.zeros(0, dtype=np.float32)
        self._projection = np.zeros((0, self._dim), dtype=np.float32)
        self._model_hash = _STATE_UNFITTED

    def _tokenize_text(self, text: str) -> list[str]:
        normalized = normalize_embedding_text(text)
        if not normalized:
            return []

        tokens: list[str] = []
        tokens.extend(_WORD_RE.findall(normalized))
        for block in _CJK_BLOCK_RE.findall(normalized):
            if len(block) == 1:
                tokens.append(block)
                continue
            tokens.extend(block[index : index + 2] for index in range(len(block) - 1))
            if len(block) >= 3:
                tokens.extend(block[index : index + 3] for index in range(len(block) - 2))

        tokens.extend(self._extract_concept_tokens(normalized))
        return tokens

    def _extract_concept_tokens(self, normalized_text: str) -> list[str]:
        concepts: list[str] = []
        for entry in self._lexicon_entries:
            matched = False
            for term in entry.all_terms:
                if normalize_embedding_text(term) in normalized_text:
                    matched = True
                    break
            if matched:
                concepts.append(f"concept::{entry.lexicon_id}")
        return concepts

    def _build_auxiliary_documents(self) -> list[list[str]]:
        auxiliary_docs: list[list[str]] = []
        for entry in self._lexicon_entries:
            concept_token = f"concept::{entry.lexicon_id}"
            auxiliary_tokens = [concept_token]
            for term in entry.all_terms:
                auxiliary_tokens.extend(self._tokenize_text(term))
            auxiliary_docs.append(auxiliary_tokens)
        return auxiliary_docs

    @staticmethod
    def _build_vocabulary(tokenized_docs: list[list[str]]) -> list[str]:
        document_frequency: Counter[str] = Counter()
        total_frequency: Counter[str] = Counter()
        for tokens in tokenized_docs:
            if not tokens:
                continue
            total_frequency.update(tokens)
            document_frequency.update(set(tokens))

        ranked_tokens = sorted(
            document_frequency,
            key=lambda token: (
                -document_frequency[token],
                -total_frequency[token],
                token,
            ),
        )
        return ranked_tokens[:_MAX_VOCAB]

    def _build_tfidf_matrix(self, tokenized_docs: list[list[str]]) -> np.ndarray:
        if not self._vocabulary:
            return np.zeros((len(tokenized_docs), 0), dtype=np.float32)

        idf = self._compute_idf(tokenized_docs)
        matrix = np.zeros((len(tokenized_docs), len(self._vocabulary)), dtype=np.float32)
        for row_index, tokens in enumerate(tokenized_docs):
            matrix[row_index] = self._build_tfidf_vector(tokens, idf_override=idf)
        return matrix

    def _compute_idf(self, tokenized_docs: list[list[str]]) -> np.ndarray:
        doc_count = max(1, len(tokenized_docs))
        document_frequency = np.zeros(len(self._vocabulary), dtype=np.float32)
        for tokens in tokenized_docs:
            seen = {self._vocab_index[token] for token in set(tokens) if token in self._vocab_index}
            for index in seen:
                document_frequency[index] += 1.0
        return np.log((1.0 + doc_count) / (1.0 + document_frequency)) + 1.0

    def _fit_projection(self, matrix: np.ndarray) -> np.ndarray:
        vocab_size = len(self._vocabulary)
        if matrix.size == 0 or vocab_size == 0:
            return np.zeros((vocab_size, self._dim), dtype=np.float32)

        _, _, vt = np.linalg.svd(matrix, full_matrices=False)
        rank = min(self._dim, vt.shape[0])
        projection = np.zeros((vocab_size, self._dim), dtype=np.float32)
        projection[:, :rank] = vt[:rank].T.astype(np.float32)
        return projection

    def _project_tokens(
        self,
        tokens: list[str],
        *,
        idf_override: np.ndarray | None = None,
    ) -> np.ndarray:
        tfidf = self._build_tfidf_vector(tokens, idf_override=idf_override)
        if self._projection.size == 0:
            return np.zeros(self._dim, dtype=np.float32)
        return tfidf @ self._projection

    def _build_tfidf_vector(
        self,
        tokens: list[str],
        *,
        idf_override: np.ndarray | None = None,
    ) -> np.ndarray:
        idf = self._idf if idf_override is None else idf_override
        tfidf = np.zeros(len(self._vocabulary), dtype=np.float32)
        if not self._vocabulary:
            return tfidf

        counts = Counter(token for token in tokens if token in self._vocab_index)
        if not counts:
            return tfidf

        total = float(sum(counts.values()))
        for token, count in counts.items():
            index = self._vocab_index[token]
            tf = 1.0 + math.log(float(count))
            tfidf[index] = (tf / total) * float(idf[index])
        return tfidf

    @staticmethod
    def _normalize_vector(vector: np.ndarray) -> np.ndarray:
        array = np.asarray(vector, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(array)
        if norm > 0:
            array = array / norm
        return array.astype(np.float32)

    def _compute_model_hash(self) -> str:
        payload = {
            "model_name": self.MODEL_NAME,
            "dim": self._dim,
            "vocabulary": self._vocabulary,
            "idf": self._idf.round(6).tolist(),
            "projection": self._projection.round(6).tolist(),
        }
        digest = hashlib.md5(  # noqa: S324 - stable local artifact fingerprint
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()
        return digest


# Backward-compatible alias for older imports inside this repo.
LocalNgramEmbedder = LocalSemanticEmbedder

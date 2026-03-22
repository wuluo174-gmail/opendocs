"""Score normalization and fusion for hybrid retrieval."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from opendocs.config.settings import RetrievalSettings


@dataclass(frozen=True)
class ScoreBreakdown:
    lexical_raw: float
    lexical_normalized: float
    dense_raw: float
    dense_normalized: float
    freshness_boost: float
    hybrid_score: float


def normalize_bm25(scores: list[float]) -> list[float]:
    """Normalize BM25 scores to [0, 1]. BM25 returns negative (more negative = better)."""
    if not scores:
        return []
    # Invert: more negative → higher positive
    positives = [-s for s in scores]
    lo, hi = min(positives), max(positives)
    if hi == lo:
        return [1.0] * len(scores)
    return [(p - lo) / (hi - lo) for p in positives]


def normalize_cosine(distances: list[float]) -> list[float]:
    """Convert cosine distances to [0, 1] similarity. Distance in [0, 2]."""
    return [max(0.0, 1.0 - d) for d in distances]


def compute_freshness(modified_at: datetime, now: datetime) -> float:
    """Exponential decay freshness. Half-life ~30 days."""
    age_days = max(0.0, (now - modified_at).total_seconds() / 86400.0)
    return math.exp(-0.023 * age_days)


def fuse_scores(
    lex: float,
    dense: float,
    fresh: float,
    settings: RetrievalSettings | None = None,
) -> float:
    """Compute hybrid score from normalized components."""
    s = settings or RetrievalSettings()
    return s.fts_weight * lex + s.dense_weight * dense + s.freshness_weight * fresh

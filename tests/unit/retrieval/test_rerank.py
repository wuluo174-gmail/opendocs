"""Unit tests for score normalization and fusion."""

from datetime import datetime, timedelta

from opendocs.config.settings import RetrievalSettings
from opendocs.retrieval.rerank import (
    compute_freshness,
    fuse_scores,
    normalize_bm25,
    normalize_cosine,
)


class TestNormalizeBm25:
    def test_empty(self) -> None:
        assert normalize_bm25([]) == []

    def test_single_score(self) -> None:
        assert normalize_bm25([-5.0]) == [1.0]

    def test_two_scores(self) -> None:
        # More negative = better → higher normalized
        result = normalize_bm25([-10.0, -2.0])
        assert result[0] > result[1]  # -10 is better → higher
        assert abs(result[0] - 1.0) < 1e-6
        assert abs(result[1] - 0.0) < 1e-6

    def test_all_same(self) -> None:
        result = normalize_bm25([-5.0, -5.0, -5.0])
        assert all(abs(x - 1.0) < 1e-6 for x in result)


class TestNormalizeCosine:
    def test_zero_distance(self) -> None:
        assert normalize_cosine([0.0]) == [1.0]

    def test_max_distance(self) -> None:
        assert normalize_cosine([2.0]) == [0.0]

    def test_negative_clamped(self) -> None:
        result = normalize_cosine([2.5])
        assert result[0] == 0.0

    def test_typical(self) -> None:
        result = normalize_cosine([0.3, 0.8])
        assert abs(result[0] - 0.7) < 1e-6
        assert abs(result[1] - 0.2) < 1e-6


class TestFreshness:
    def test_today_is_one(self) -> None:
        now = datetime(2026, 3, 20)
        assert abs(compute_freshness(now, now) - 1.0) < 1e-6

    def test_30_days_about_half(self) -> None:
        now = datetime(2026, 3, 20)
        then = now - timedelta(days=30)
        fresh = compute_freshness(then, now)
        assert 0.45 < fresh < 0.55

    def test_365_days_near_zero(self) -> None:
        now = datetime(2026, 3, 20)
        then = now - timedelta(days=365)
        fresh = compute_freshness(then, now)
        assert fresh < 0.01


class TestFuseScores:
    def test_default_weights(self) -> None:
        score = fuse_scores(1.0, 1.0, 1.0)
        assert abs(score - 1.0) < 1e-6

    def test_zero_all(self) -> None:
        assert fuse_scores(0.0, 0.0, 0.0) == 0.0

    def test_only_dense(self) -> None:
        settings = RetrievalSettings()
        score = fuse_scores(0.0, 1.0, 0.0, settings)
        assert abs(score - settings.dense_weight) < 1e-6

    def test_custom_weights(self) -> None:
        settings = RetrievalSettings(fts_weight=0.5, dense_weight=0.4, freshness_weight=0.1)
        score = fuse_scores(0.8, 0.6, 1.0, settings)
        expected = 0.5 * 0.8 + 0.4 * 0.6 + 0.1 * 1.0
        assert abs(score - expected) < 1e-6

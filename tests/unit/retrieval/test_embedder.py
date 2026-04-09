"""Unit tests for the local corpus-trained semantic embedder."""

from __future__ import annotations

import numpy as np
import pytest

from opendocs.retrieval.embedder import (
    LocalSemanticEmbedder,
    build_dense_model_path,
    normalize_embedding_text,
)


@pytest.fixture()
def embedder(tmp_path) -> LocalSemanticEmbedder:
    model_path = build_dense_model_path(tmp_path / "test.hnsw")
    return LocalSemanticEmbedder(model_path=model_path)


class TestNormalization:
    def test_normalize_embedding_text_owns_casefolded_dense_semantics(self) -> None:
        assert normalize_embedding_text(" ＡＩ ") == "ai"

    def test_empty_returns_zero_without_model(self, embedder: LocalSemanticEmbedder) -> None:
        vec = embedder.embed_text("")
        assert np.allclose(vec, 0.0)


class TestTrainingLifecycle:
    def test_default_dim(self, embedder: LocalSemanticEmbedder) -> None:
        assert embedder.dim == 128

    def test_fit_makes_embeddings_non_zero(self, embedder: LocalSemanticEmbedder) -> None:
        embedder.fit_corpus(
            [
                "Project budget approved for the next phase.",
                "Authentication module review completed.",
            ]
        )
        vec = embedder.embed_text("budget plan")
        assert vec.shape == (128,)
        assert np.linalg.norm(vec) > 0

    def test_fit_is_deterministic_for_same_corpus(self, tmp_path) -> None:
        corpus = [
            "Atlas 项目负责人是王敏。",
            "Authentication module review completed.",
        ]
        first = LocalSemanticEmbedder(model_path=build_dense_model_path(tmp_path / "a.hnsw"))
        second = LocalSemanticEmbedder(model_path=build_dense_model_path(tmp_path / "b.hnsw"))

        first.fit_corpus(corpus)
        second.fit_corpus(corpus)

        assert first.fingerprint == second.fingerprint
        assert np.allclose(
            first.embed_text("Atlas 项目负责人"),
            second.embed_text("Atlas 项目负责人"),
        )

    def test_model_can_roundtrip_through_disk(self, tmp_path) -> None:
        model_path = build_dense_model_path(tmp_path / "roundtrip.hnsw")
        embedder = LocalSemanticEmbedder(model_path=model_path)
        corpus = [
            "Project budget approved for the next phase.",
            "Authentication module review completed.",
        ]
        embedder.fit_corpus(corpus)
        expected = embedder.embed_text("cost plan")
        expected_fingerprint = embedder.fingerprint
        embedder.save_model()

        reloaded = LocalSemanticEmbedder(model_path=model_path)
        actual = reloaded.embed_text("cost plan")

        assert reloaded.fingerprint == expected_fingerprint
        assert np.allclose(actual, expected)


class TestSemanticBehavior:
    def test_runtime_owned_budget_concept_bridges_cost_plan_and_budget(
        self,
        embedder: LocalSemanticEmbedder,
    ) -> None:
        embedder.fit_corpus(
            [
                "Project budget approved for the next phase.",
                "Identity provider integration is pending review.",
            ]
        )
        query = embedder.embed_text("cost plan")
        budget_doc = embedder.embed_text("Project budget approved for the next phase.")
        unrelated_doc = embedder.embed_text("Identity provider integration is pending review.")

        assert float(np.dot(query, budget_doc)) > float(np.dot(query, unrelated_doc))

    def test_runtime_owned_login_concept_bridges_cross_language_aliases(
        self,
        embedder: LocalSemanticEmbedder,
    ) -> None:
        embedder.fit_corpus(
            [
                "Completed authentication module review and testing.",
                "Weekly status update about deployment progress.",
            ]
        )
        query = embedder.embed_text("身份验证模块")
        auth_doc = embedder.embed_text("Completed authentication module review and testing.")
        other_doc = embedder.embed_text("Weekly status update about deployment progress.")

        assert float(np.dot(query, auth_doc)) > float(np.dot(query, other_doc))

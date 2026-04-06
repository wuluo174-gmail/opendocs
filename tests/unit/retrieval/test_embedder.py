"""Unit tests for LocalNgramEmbedder."""

import numpy as np
import pytest

from opendocs.retrieval.embedder import LocalNgramEmbedder, normalize_embedding_text


@pytest.fixture()
def embedder() -> LocalNgramEmbedder:
    return LocalNgramEmbedder()


class TestDimension:
    def test_default_dim(self, embedder: LocalNgramEmbedder) -> None:
        assert embedder.dim == 128

    def test_output_shape(self, embedder: LocalNgramEmbedder) -> None:
        vec = embedder.embed_text("hello world")
        assert vec.shape == (128,)
        assert vec.dtype == np.float32


class TestNormalization:
    def test_normalize_embedding_text_owns_casefolded_dense_semantics(self) -> None:
        assert normalize_embedding_text(" ＡＩ ") == "ai"

    def test_l2_normalized(self, embedder: LocalNgramEmbedder) -> None:
        vec = embedder.embed_text("test document text")
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-5

    def test_empty_returns_zero(self, embedder: LocalNgramEmbedder) -> None:
        vec = embedder.embed_text("")
        assert np.allclose(vec, 0.0)

    def test_whitespace_returns_zero(self, embedder: LocalNgramEmbedder) -> None:
        vec = embedder.embed_text("   ")
        assert np.allclose(vec, 0.0)


class TestDeterminism:
    def test_same_text_same_vector(self, embedder: LocalNgramEmbedder) -> None:
        v1 = embedder.embed_text("项目进度报告")
        v2 = embedder.embed_text("项目进度报告")
        assert np.allclose(v1, v2)

    def test_case_and_fullwidth_variants_share_the_same_vector(
        self,
        embedder: LocalNgramEmbedder,
    ) -> None:
        canonical = embedder.embed_text("AI")
        lowercase = embedder.embed_text("ai")
        fullwidth = embedder.embed_text("ＡＩ")
        assert np.allclose(canonical, lowercase)
        assert np.allclose(canonical, fullwidth)

    def test_different_text_different_vector(self, embedder: LocalNgramEmbedder) -> None:
        v1 = embedder.embed_text("项目进度报告")
        v2 = embedder.embed_text("meeting notes summary")
        assert not np.allclose(v1, v2)


class TestCJK:
    def test_cjk_non_zero(self, embedder: LocalNgramEmbedder) -> None:
        vec = embedder.embed_text("项目进度")
        assert np.linalg.norm(vec) > 0

    def test_cjk_similarity(self, embedder: LocalNgramEmbedder) -> None:
        q = embedder.embed_text("项目")
        doc = embedder.embed_text("本项目的目标是开发文档管理工具")
        other = embedder.embed_text("weekly status report completed")
        sim_match = float(np.dot(q, doc))
        sim_other = float(np.dot(q, other))
        assert sim_match > sim_other


class TestBatch:
    def test_batch_matches_single(self, embedder: LocalNgramEmbedder) -> None:
        texts = ["hello", "world", "项目"]
        batch = embedder.embed_batch(texts)
        assert batch.shape == (3, 128)
        for i, t in enumerate(texts):
            single = embedder.embed_text(t)
            assert np.allclose(batch[i], single)

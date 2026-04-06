"""Unit tests for the shared retrieval stage asset loader."""

from __future__ import annotations

import json

import pytest

from opendocs.retrieval.query_lexicon import RUNTIME_QUERY_LEXICON_ASSET_REF
from opendocs.retrieval.stage_asset_loader import (
    read_stage_asset_text,
    stage_asset_relative_path,
)
from opendocs.retrieval.stage_golden_queries import S4_HYBRID_SEARCH_QUERIES_ASSET_REF


class TestStageAssetLoader:
    def test_reads_stage_asset_via_asset_ref(self) -> None:
        payload = json.loads(read_stage_asset_text(RUNTIME_QUERY_LEXICON_ASSET_REF))
        assert "entries" in payload
        assert payload["entries"]

    def test_returns_relative_asset_path_from_stage_owner(self) -> None:
        assert str(stage_asset_relative_path(S4_HYBRID_SEARCH_QUERIES_ASSET_REF)) == (
            "s4_hybrid_search_queries.json"
        )

    def test_rejects_non_stage_asset_refs(self) -> None:
        with pytest.raises(ValueError, match="unsupported retrieval stage asset ref"):
            stage_asset_relative_path("docs/acceptance/acceptance_cases.md")

    def test_rejects_parent_path_traversal_within_stage_owner_prefix(self) -> None:
        with pytest.raises(
            ValueError, match="retrieval stage asset ref must stay within asset root"
        ):
            stage_asset_relative_path("src/opendocs/retrieval/assets/../stage_search_corpus.py")

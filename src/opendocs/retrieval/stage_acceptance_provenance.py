"""Stage-owned provenance builders for S4 acceptance artifact manifests."""

from __future__ import annotations

from opendocs.retrieval.stage_acceptance_capture_cases import (
    S4_ACCEPTANCE_CAPTURE_CASES_ASSET_REF,
)
from opendocs.retrieval.stage_acceptance_corpora import S4_ACCEPTANCE_CORPORA_ASSET_REF
from opendocs.retrieval.query_lexicon import S4_QUERY_LEXICON_ASSET_REF
from opendocs.retrieval.stage_filter_cases import S4_SEARCH_FILTER_CASES_ASSET_REF
from opendocs.retrieval.stage_golden_queries import S4_HYBRID_SEARCH_QUERIES_ASSET_REF
from opendocs.retrieval.stage_search_corpus import (
    S4_SEARCH_CORPUS_BUILDER_REF,
    S4_SEARCH_SOURCE_DEFAULTS_REF,
)


def build_s4_tc018_input_provenance() -> dict[str, str]:
    return {
        "acceptance_corpus_asset": S4_ACCEPTANCE_CORPORA_ASSET_REF,
        "acceptance_capture_asset": S4_ACCEPTANCE_CAPTURE_CASES_ASSET_REF,
    }


def build_s4_tc005_input_provenance() -> dict[str, str]:
    return {
        "acceptance_corpus_asset": S4_ACCEPTANCE_CORPORA_ASSET_REF,
        "acceptance_capture_asset": S4_ACCEPTANCE_CAPTURE_CASES_ASSET_REF,
        "query_lexicon_asset": S4_QUERY_LEXICON_ASSET_REF,
        "golden_queries_asset": S4_HYBRID_SEARCH_QUERIES_ASSET_REF,
        "filter_cases_asset": S4_SEARCH_FILTER_CASES_ASSET_REF,
        "corpus_builder": S4_SEARCH_CORPUS_BUILDER_REF,
        "source_defaults_owner": S4_SEARCH_SOURCE_DEFAULTS_REF,
    }

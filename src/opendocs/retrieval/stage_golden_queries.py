"""Stage-scoped golden query assets for S4 retrieval verification."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from opendocs.retrieval.query_lexicon import (
    build_runtime_query_lexicon_index,
    normalize_query_lookup_key,
)
from opendocs.retrieval.stage_asset_loader import read_stage_asset_text
from opendocs.retrieval.stage_search_corpus import list_s4_search_corpus_documents

S4_HYBRID_SEARCH_QUERIES_ASSET_REF = "src/opendocs/retrieval/assets/s4_hybrid_search_queries.json"


@dataclass(frozen=True)
class StageGoldenQuery:
    query_id: str
    query_type: str
    query: str
    expect_doc: str | None
    lexicon_id: str | None
    expect_empty: bool


S4_EXPECTED_LOCATING_QUERY_COUNT = 5
S4_EXPECTED_SYNONYM_QUERY_COUNT = 5
S4_EXPECTED_ZERO_QUERY_COUNT = 1


@lru_cache(maxsize=1)
def load_s4_hybrid_search_queries() -> tuple[StageGoldenQuery, ...]:
    """Load and validate the stage-owned S4 golden hybrid search queries."""
    payload = json.loads(read_stage_asset_text(S4_HYBRID_SEARCH_QUERIES_ASSET_REF))
    raw_queries = payload.get("queries")
    if not isinstance(raw_queries, list):
        raise ValueError("S4 golden queries must contain a 'queries' list")

    lexicon_by_id = build_runtime_query_lexicon_index()
    corpus_documents = set(list_s4_search_corpus_documents())
    queries: list[StageGoldenQuery] = []
    seen_ids: set[str] = set()
    seen_synonym_lexicon_ids: set[str] = set()
    locating_count = 0
    synonym_count = 0
    zero_count = 0

    for raw_query in raw_queries:
        if not isinstance(raw_query, dict):
            raise ValueError("S4 golden queries must be objects")

        query_id = str(raw_query.get("id", "")).strip()
        query_type = str(raw_query.get("type", "")).strip()
        query = str(raw_query.get("query", "")).strip()
        expect_doc = str(raw_query.get("expect_doc", "")).strip() or None
        lexicon_id_value = raw_query.get("lexicon_id")
        lexicon_id = str(lexicon_id_value).strip() if lexicon_id_value is not None else None
        expect_empty = raw_query.get("expect_empty") is True

        if not query_id:
            raise ValueError(f"S4 golden query missing id: {raw_query!r}")
        if query_id in seen_ids:
            raise ValueError(f"duplicate S4 golden query id: {query_id}")
        if query_type not in {"locating", "synonym", "zero"}:
            raise ValueError(f"unsupported S4 golden query type: {query_type!r}")
        if not query:
            raise ValueError(f"S4 golden query missing query text: {query_id}")

        if query_type == "zero":
            zero_count += 1
            if not expect_empty:
                raise ValueError(f"S4 zero query must set expect_empty=true: {query_id}")
            if expect_doc is not None or lexicon_id is not None:
                raise ValueError(
                    f"S4 zero query must not define expect_doc or lexicon_id: {query_id}"
                )
        elif query_type == "locating":
            locating_count += 1
            if expect_doc is None:
                raise ValueError(f"S4 locating query missing expect_doc: {query_id}")
            if expect_doc not in corpus_documents:
                raise ValueError(
                    f"S4 locating query references unknown corpus document: {query_id}"
                )
            if lexicon_id is not None or expect_empty:
                raise ValueError(
                    f"S4 locating query contains invalid synonym/zero fields: {query_id}"
                )
        else:
            synonym_count += 1
            if lexicon_id is None:
                raise ValueError(f"S4 synonym query missing lexicon_id: {query_id}")
            if expect_doc is None:
                raise ValueError(f"S4 synonym query missing expect_doc: {query_id}")
            if expect_doc not in corpus_documents:
                raise ValueError(f"S4 synonym query references unknown corpus document: {query_id}")
            entry = lexicon_by_id.get(lexicon_id)
            if entry is None:
                raise ValueError(f"S4 synonym query references unknown lexicon_id: {lexicon_id}")
            if not _entry_contains_alias(entry, query):
                raise ValueError(
                    f"S4 golden synonym query drift: {lexicon_id} does not contain alias {query!r}"
                )
            if lexicon_id in seen_synonym_lexicon_ids:
                raise ValueError(f"duplicate S4 synonym lexicon_id: {lexicon_id}")
            seen_synonym_lexicon_ids.add(lexicon_id)

        seen_ids.add(query_id)
        queries.append(
            StageGoldenQuery(
                query_id=query_id,
                query_type=query_type,
                query=query,
                expect_doc=expect_doc,
                lexicon_id=lexicon_id,
                expect_empty=expect_empty,
            )
        )

    if locating_count != S4_EXPECTED_LOCATING_QUERY_COUNT:
        raise ValueError(
            f"S4 locating query count drift: {locating_count} != {S4_EXPECTED_LOCATING_QUERY_COUNT}"
        )
    if synonym_count != S4_EXPECTED_SYNONYM_QUERY_COUNT:
        raise ValueError(
            f"S4 synonym query count drift: {synonym_count} != {S4_EXPECTED_SYNONYM_QUERY_COUNT}"
        )
    if zero_count != S4_EXPECTED_ZERO_QUERY_COUNT:
        raise ValueError(
            f"S4 zero query count drift: {zero_count} != {S4_EXPECTED_ZERO_QUERY_COUNT}"
        )
    return tuple(queries)


def _entry_contains_alias(entry, query: str) -> bool:
    query_lookup_key = normalize_query_lookup_key(query)
    return any(normalize_query_lookup_key(alias) == query_lookup_key for alias in entry.aliases)

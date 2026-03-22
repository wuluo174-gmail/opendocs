"""Query preprocessing for FTS5 trigram search.

Normalizes user queries, expands stage-scoped synonym variants, and sanitizes
FTS5 syntax without adding LIKE fallback paths.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from opendocs.retrieval.query_lexicon import (
    build_stage_query_expansion_index,
    normalize_query_lookup_key,
    normalize_query_text,
    parse_query_expansion_index,
)


@dataclass(frozen=True)
class QueryVariant:
    """One normalized retrieval variant for a single user query."""

    text: str
    fts_query: str | None


@dataclass(frozen=True)
class PreparedQuery:
    """Structured query intent shared by lexical and dense retrieval."""

    variants: tuple[QueryVariant, ...]

    @property
    def fts_query(self) -> str | None:
        return self.variants[0].fts_query

    @property
    def raw_normalized(self) -> str:
        return self.variants[0].text


# Characters that break FTS5 MATCH syntax when unbalanced/orphaned.
_FTS5_UNSAFE = re.compile(r"[*^{}():]")


class QueryPreprocessor:
    """Transform user queries into a retrieval-ready intent object.

    The preprocessor owns normalization and stage-scoped synonym expansion, so
    downstream lexical and dense search operate on the same query variants.
    """

    def __init__(self, expansions: Mapping[str, Sequence[str]] | None = None) -> None:
        if expansions is None:
            self._expansions = build_stage_query_expansion_index()
            return
        self._expansions = parse_query_expansion_index(dict(expansions))

    def prepare(self, query: str) -> PreparedQuery:
        """Normalize and sanitize a query for FTS5 + dense search.

        Raises:
            ValueError: If query is empty or only whitespace/punctuation.
        """
        if not query or not query.strip():
            raise ValueError("empty query")

        raw_normalized = normalize_query_text(query)
        if not raw_normalized:
            raise ValueError("empty query after normalization")

        variants = tuple(
            QueryVariant(text=text, fts_query=_sanitize_fts_query(text))
            for text in self._expand_variants(raw_normalized)
        )
        return PreparedQuery(variants=variants)

    def _expand_variants(self, raw_normalized: str) -> tuple[str, ...]:
        return (raw_normalized, *self._expansions.get(normalize_query_lookup_key(raw_normalized), ()))


def _sanitize_fts_query(text: str) -> str | None:
    fts_text = _FTS5_UNSAFE.sub(" ", text)
    fts_text = _strip_unbalanced_quotes(fts_text)
    fts_text = " ".join(fts_text.split())
    return fts_text if fts_text else None


def _strip_unbalanced_quotes(text: str) -> str:
    """Remove double quotes if they are not balanced."""
    count = text.count('"')
    if count % 2 != 0:
        return text.replace('"', "")
    return text

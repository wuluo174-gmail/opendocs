"""Query preprocessing for FTS5 trigram search.

Normalizes human query text once, then derives a safe FTS MATCH expression from
that semantic query. The lexical channel owns MATCH syntax; downstream callers
should never treat raw user input as an FTS program.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from opendocs.retrieval.query_lexicon import (
    build_runtime_query_expansion_index,
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


_FTS5_STRIP_CHARS = re.compile(r"[*^{}():]")
_FTS5_TOKEN_RE = re.compile(r'"[^"]+"|\S+')
_FTS5_OPERATOR_TOKENS = frozenset({"AND", "OR", "NOT"})
_FTS5_BARE_TOKEN_RE = re.compile(r"^[0-9A-Za-z_\u0080-\uffff]+$")
_FTS5_SEARCHABLE_TOKEN_RE = re.compile(r"[0-9A-Za-z\u0080-\uffff]")


class QueryPreprocessor:
    """Transform user queries into a retrieval-ready intent object.

    The preprocessor owns normalization and runtime-owned synonym expansion, so
    downstream lexical and dense search operate on the same query variants.
    """

    def __init__(self, expansions: Mapping[str, Sequence[str]] | None = None) -> None:
        if expansions is None:
            self._expansions = build_runtime_query_expansion_index()
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
        return (
            raw_normalized,
            *self._expansions.get(normalize_query_lookup_key(raw_normalized), ()),
        )


def _sanitize_fts_query(text: str) -> str | None:
    fts_text = _strip_unbalanced_quotes(text)
    fts_text = _FTS5_STRIP_CHARS.sub(" ", fts_text)
    tokens = _FTS5_TOKEN_RE.findall(fts_text)
    if not tokens:
        return None

    normalized_tokens: list[str] = []
    for token in tokens:
        normalized = _normalize_fts_token(token)
        if normalized is not None:
            normalized_tokens.append(normalized)

    if not normalized_tokens:
        return None
    return " ".join(normalized_tokens)


def _strip_unbalanced_quotes(text: str) -> str:
    """Remove double quotes if they are not balanced."""
    count = text.count('"')
    if count % 2 != 0:
        return text.replace('"', "")
    return text


def _normalize_fts_token(token: str) -> str | None:
    stripped = token.strip()
    if not stripped:
        return None

    if stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2:
        phrase = stripped[1:-1].strip()
        if not _FTS5_SEARCHABLE_TOKEN_RE.search(phrase):
            return None
        escaped_phrase = phrase.replace('"', '""')
        return f'"{escaped_phrase}"'

    if stripped in _FTS5_OPERATOR_TOKENS:
        return stripped

    if not _FTS5_SEARCHABLE_TOKEN_RE.search(stripped):
        return None
    if _FTS5_BARE_TOKEN_RE.fullmatch(stripped):
        return stripped

    escaped = stripped.replace('"', '""')
    return f'"{escaped}"'

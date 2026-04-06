"""Runtime-owned synonym lexicon assets for retrieval."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from opendocs.parsers.normalization import normalize_text
from opendocs.retrieval.stage_asset_loader import read_stage_asset_text

RUNTIME_QUERY_LEXICON_ASSET_REF = "src/opendocs/retrieval/assets/query_lexicon.json"
# Backward-compatible alias for older acceptance/test helpers.
S4_QUERY_LEXICON_ASSET_REF = RUNTIME_QUERY_LEXICON_ASSET_REF


@dataclass(frozen=True)
class QueryLexiconEntry:
    """One curated synonym cluster owned by the retrieval runtime."""

    lexicon_id: str
    canonical_query: str
    aliases: tuple[str, ...]

    @property
    def all_terms(self) -> tuple[str, ...]:
        return (self.canonical_query, *self.aliases)

    def contains_query(self, query: str) -> bool:
        lookup_key = normalize_query_lookup_key(query)
        return any(
            normalize_query_lookup_key(candidate) == lookup_key for candidate in self.all_terms
        )


def normalize_query_text(text: str) -> str:
    """Normalize human-entered query text into the retrieval canonical form."""
    return normalize_text(text).strip()


def normalize_query_lookup_key(text: str) -> str:
    """Normalize query text for case-insensitive lookup and uniqueness checks."""
    return normalize_query_text(text).casefold()


def parse_query_lexicon_entries(raw_entries: object) -> tuple[QueryLexiconEntry, ...]:
    """Parse and validate raw synonym clusters into normalized retrieval objects."""
    if not isinstance(raw_entries, list):
        raise ValueError("runtime query lexicon must contain an 'entries' list")

    entries: list[QueryLexiconEntry] = []
    seen_ids: set[str] = set()
    seen_lookup_keys: dict[str, str] = {}
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise ValueError("runtime query lexicon entries must be objects")

        lexicon_id = str(raw_entry.get("lexicon_id", "")).strip()
        canonical_query = normalize_query_text(str(raw_entry.get("canonical_query", "")))
        raw_aliases = raw_entry.get("aliases")
        if not lexicon_id:
            raise ValueError("runtime query lexicon entry missing lexicon_id")
        if not canonical_query:
            raise ValueError(f"runtime query lexicon entry '{lexicon_id}' missing canonical_query")
        aliases = _normalize_aliases(
            owner_label=f"runtime query lexicon entry '{lexicon_id}'",
            canonical_query=canonical_query,
            raw_aliases=raw_aliases,
        )
        if lexicon_id in seen_ids:
            raise ValueError(f"duplicate runtime query lexicon id: {lexicon_id}")

        for term in (canonical_query, *aliases):
            lookup_key = normalize_query_lookup_key(term)
            if lookup_key in seen_lookup_keys:
                raise ValueError(
                    "duplicate runtime query term after normalization: "
                    f"{term} conflicts with {seen_lookup_keys[lookup_key]}"
                )
            seen_lookup_keys[lookup_key] = term

        seen_ids.add(lexicon_id)
        entries.append(
            QueryLexiconEntry(
                lexicon_id=lexicon_id,
                canonical_query=canonical_query,
                aliases=aliases,
            )
        )

    return tuple(entries)


def parse_query_expansion_index(raw_expansions: object) -> dict[str, tuple[str, ...]]:
    """Parse caller-provided directional query expansions."""
    if not isinstance(raw_expansions, dict):
        raise ValueError("query expansion map must be an object")

    expansion_index: dict[str, tuple[str, ...]] = {}
    seen_lookup_keys: dict[str, str] = {}
    for raw_trigger_query, raw_values in raw_expansions.items():
        trigger_query = normalize_query_text(str(raw_trigger_query))
        if not trigger_query:
            raise ValueError("query expansion map contains empty trigger_query")

        expansions = _normalize_expansions(
            owner_label=f"query expansion '{trigger_query}'",
            trigger_query=trigger_query,
            raw_expansions=raw_values,
            duplicate_label="query expansion",
        )
        lookup_key = normalize_query_lookup_key(trigger_query)
        if lookup_key in seen_lookup_keys:
            raise ValueError(
                "duplicate query expansion trigger after normalization: "
                f"{trigger_query} conflicts with {seen_lookup_keys[lookup_key]}"
            )

        seen_lookup_keys[lookup_key] = trigger_query
        expansion_index[lookup_key] = expansions

    return expansion_index


def build_query_expansion_index(
    entries: tuple[QueryLexiconEntry, ...],
) -> dict[str, tuple[str, ...]]:
    """Expand every known alias to every peer term in the same synonym cluster."""
    expansion_index: dict[str, tuple[str, ...]] = {}
    for entry in entries:
        for term in entry.all_terms:
            lookup_key = normalize_query_lookup_key(term)
            expansion_index[lookup_key] = tuple(
                candidate
                for candidate in entry.all_terms
                if normalize_query_lookup_key(candidate) != lookup_key
            )
    return expansion_index


@lru_cache(maxsize=1)
def load_runtime_query_lexicon() -> tuple[QueryLexiconEntry, ...]:
    """Load the retrieval runtime synonym lexicon from packaged JSON data."""
    payload = json.loads(read_stage_asset_text(RUNTIME_QUERY_LEXICON_ASSET_REF))
    return parse_query_lexicon_entries(payload.get("entries"))


def build_runtime_query_expansion_index() -> dict[str, tuple[str, ...]]:
    """Return the retrieval expansion index keyed by normalized lookup key."""
    return build_query_expansion_index(load_runtime_query_lexicon())


def build_runtime_query_lexicon_index() -> dict[str, QueryLexiconEntry]:
    """Return the runtime lexicon keyed by stable lexicon_id."""
    return {entry.lexicon_id: entry for entry in load_runtime_query_lexicon()}


# Backward-compatible aliases used by older test helpers.
load_stage_query_lexicon = load_runtime_query_lexicon
build_stage_query_expansion_index = build_runtime_query_expansion_index
build_stage_query_lexicon_index = build_runtime_query_lexicon_index


def _normalize_aliases(
    *,
    owner_label: str,
    canonical_query: str,
    raw_aliases: object,
) -> tuple[str, ...]:
    if not isinstance(raw_aliases, (list, tuple)) or not raw_aliases:
        raise ValueError(f"{owner_label} missing aliases")

    normalized: list[str] = []
    seen_lookup_keys: dict[str, str] = {}
    canonical_lookup_key = normalize_query_lookup_key(canonical_query)
    for raw_value in raw_aliases:
        value = normalize_query_text(str(raw_value))
        if not value:
            raise ValueError(f"{owner_label} has empty alias")
        lookup_key = normalize_query_lookup_key(value)
        if lookup_key == canonical_lookup_key:
            raise ValueError(
                f"{owner_label} alias duplicates canonical_query after normalization: {value}"
            )
        if lookup_key in seen_lookup_keys:
            raise ValueError(
                f"duplicate query alias after normalization in '{owner_label}': "
                f"{value} conflicts with {seen_lookup_keys[lookup_key]}"
            )
        seen_lookup_keys[lookup_key] = value
        normalized.append(value)
    return tuple(normalized)


def _normalize_expansions(
    *,
    owner_label: str,
    trigger_query: str,
    raw_expansions: object,
    duplicate_label: str,
) -> tuple[str, ...]:
    if not isinstance(raw_expansions, (list, tuple)) or not raw_expansions:
        raise ValueError(f"{owner_label} missing expansions")

    normalized: list[str] = []
    seen_lookup_keys: dict[str, str] = {}
    trigger_lookup_key = normalize_query_lookup_key(trigger_query)
    for raw_value in raw_expansions:
        value = normalize_query_text(str(raw_value))
        if not value:
            raise ValueError(f"{owner_label} has empty expansion")
        lookup_key = normalize_query_lookup_key(value)
        if lookup_key == trigger_lookup_key:
            raise ValueError(
                f"{owner_label} expansion duplicates trigger_query after normalization: {value}"
            )
        if lookup_key in seen_lookup_keys:
            raise ValueError(
                f"duplicate {duplicate_label} after normalization in '{owner_label}': "
                f"{value} conflicts with {seen_lookup_keys[lookup_key]}"
            )
        seen_lookup_keys[lookup_key] = value
        normalized.append(value)
    return tuple(normalized)

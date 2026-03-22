"""Stage-scoped synonym lexicon assets for retrieval."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from opendocs.parsers.normalization import normalize_text
from opendocs.retrieval.stage_asset_loader import read_stage_asset_text

S4_QUERY_LEXICON_ASSET_REF = "src/opendocs/retrieval/assets/stage_query_lexicon.json"


@dataclass(frozen=True)
class QueryLexiconEntry:
    """One curated synonym entry owned by the retrieval layer."""

    lexicon_id: str
    trigger_query: str
    expansions: tuple[str, ...]

    @property
    def lookup_key(self) -> str:
        return normalize_query_lookup_key(self.trigger_query)


def normalize_query_text(text: str) -> str:
    """Normalize human-entered query text into the retrieval canonical form."""
    return normalize_text(text).strip()


def normalize_query_lookup_key(text: str) -> str:
    """Normalize query text for case-insensitive lookup and uniqueness checks."""
    return normalize_query_text(text).casefold()


def parse_query_lexicon_entries(raw_entries: object) -> tuple[QueryLexiconEntry, ...]:
    """Parse and validate raw lexicon entries into normalized retrieval objects."""
    if not isinstance(raw_entries, list):
        raise ValueError("stage query lexicon must contain an 'entries' list")

    entries: list[QueryLexiconEntry] = []
    seen_ids: set[str] = set()
    seen_lookup_keys: dict[str, str] = {}
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise ValueError("stage query lexicon entries must be objects")

        lexicon_id = str(raw_entry.get("lexicon_id", "")).strip()
        trigger_query = normalize_query_text(str(raw_entry.get("trigger_query", "")))
        raw_expansions = raw_entry.get("expansions")
        if not lexicon_id:
            raise ValueError("stage query lexicon entry missing lexicon_id")
        if not trigger_query:
            raise ValueError(f"stage query lexicon entry '{lexicon_id}' missing trigger_query")
        expansions = _normalize_expansions(
            owner_label=f"stage query lexicon entry '{lexicon_id}'",
            trigger_query=trigger_query,
            raw_expansions=raw_expansions,
            duplicate_label="stage query expansion",
        )
        lookup_key = normalize_query_lookup_key(trigger_query)
        if lexicon_id in seen_ids:
            raise ValueError(f"duplicate stage query lexicon id: {lexicon_id}")
        if lookup_key in seen_lookup_keys:
            raise ValueError(
                "duplicate stage query trigger after normalization: "
                f"{trigger_query} conflicts with {seen_lookup_keys[lookup_key]}"
            )

        seen_ids.add(lexicon_id)
        seen_lookup_keys[lookup_key] = trigger_query
        entries.append(
            QueryLexiconEntry(
                lexicon_id=lexicon_id,
                trigger_query=trigger_query,
                expansions=expansions,
            )
        )

    return tuple(entries)


def parse_query_expansion_index(raw_expansions: object) -> dict[str, tuple[str, ...]]:
    """Parse caller-provided query expansions with the same rules as the stage lexicon."""
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


@lru_cache(maxsize=1)
def load_stage_query_lexicon() -> tuple[QueryLexiconEntry, ...]:
    """Load the stage-scoped synonym lexicon from packaged JSON data."""
    payload = json.loads(read_stage_asset_text(S4_QUERY_LEXICON_ASSET_REF))
    return parse_query_lexicon_entries(payload.get("entries"))


def build_stage_query_expansion_index() -> dict[str, tuple[str, ...]]:
    """Return the retrieval expansion index keyed by normalized lookup key."""
    return {
        entry.lookup_key: entry.expansions
        for entry in load_stage_query_lexicon()
    }


def build_stage_query_lexicon_index() -> dict[str, QueryLexiconEntry]:
    """Return the lexicon keyed by stable lexicon_id for acceptance tests."""
    return {
        entry.lexicon_id: entry
        for entry in load_stage_query_lexicon()
    }


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
            raise ValueError(f"{owner_label} expansion duplicates trigger_query after normalization: {value}")
        if lookup_key in seen_lookup_keys:
            raise ValueError(
                f"duplicate {duplicate_label} after normalization in '{owner_label}': "
                f"{value} conflicts with {seen_lookup_keys[lookup_key]}"
            )
        seen_lookup_keys[lookup_key] = value
        normalized.append(value)
    return tuple(normalized)

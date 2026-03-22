"""Conflict detection — text-pattern based, no LLM needed."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from opendocs.retrieval.evidence import Citation, SearchResult

_NEGATION_PREFIXES = ("不", "非", "没有", "未", "无")
_AFFIRMATIVE_PREFIXES = ("已", "有", "是")

_NUMBER_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*([万亿千百十%％元美元]|million|billion|k)?", re.IGNORECASE)


def detect_conflicts(
    results: list[SearchResult],
    chunk_texts: dict[str, str],
) -> list[list[Citation]] | None:
    """Check for contradictions across documents.

    Groups results by doc_id, then compares chunk texts between
    document groups for negation patterns and numeric contradictions.

    Returns list of conflicting citation groups (each group >= 2),
    or None if no conflict detected.
    """
    by_doc: dict[str, list[SearchResult]] = defaultdict(list)
    for r in results:
        by_doc[r.doc_id].append(r)

    if len(by_doc) < 2:
        return None

    doc_ids = list(by_doc.keys())
    conflicts: list[list[Citation]] = []

    for id_a, id_b in combinations(doc_ids, 2):
        for ra in by_doc[id_a]:
            text_a = chunk_texts.get(ra.chunk_id, ra.summary)
            for rb in by_doc[id_b]:
                text_b = chunk_texts.get(rb.chunk_id, rb.summary)
                if _has_negation_conflict(text_a, text_b) or _has_numeric_conflict(text_a, text_b):
                    conflicts.append([ra.citation, rb.citation])

    return conflicts if conflicts else None


def _has_negation_conflict(text_a: str, text_b: str) -> bool:
    """Check if one text negates a claim in the other."""
    for prefix in _NEGATION_PREFIXES:
        for phrase in _extract_short_phrases(text_a):
            negated = prefix + phrase
            if negated in text_b:
                return True
        for phrase in _extract_short_phrases(text_b):
            negated = prefix + phrase
            if negated in text_a:
                return True

    # Check affirmative vs negation: "已X" in A and "未X" in B
    for aff in _AFFIRMATIVE_PREFIXES:
        for neg in _NEGATION_PREFIXES:
            for phrase in _extract_short_phrases(text_a):
                if phrase.startswith(aff):
                    base = phrase[len(aff):]
                    if base and neg + base in text_b:
                        return True
            for phrase in _extract_short_phrases(text_b):
                if phrase.startswith(aff):
                    base = phrase[len(aff):]
                    if base and neg + base in text_a:
                        return True
    return False


def _extract_short_phrases(text: str) -> list[str]:
    """Extract 2-8 char CJK phrases as assertion candidates.

    For segments longer than 8 chars, generates 4-6 char sub-phrases
    via sliding window to catch embedded assertions.
    """
    phrases: list[str] = []
    for segment in re.split(r"[，。！？；：、\s,.:;!?]+", text):
        segment = segment.strip()
        if not segment:
            continue
        if 2 <= len(segment) <= 8:
            phrases.append(segment)
        if len(segment) > 4:
            for width in range(4, min(7, len(segment) + 1)):
                for start in range(len(segment) - width + 1):
                    sub = segment[start : start + width]
                    phrases.append(sub)
    return phrases


def _has_numeric_conflict(text_a: str, text_b: str) -> bool:
    """Check if same context has different numbers."""
    nums_a = _extract_numbers_with_context(text_a)
    nums_b = _extract_numbers_with_context(text_b)

    for ctx_a, val_a in nums_a:
        for ctx_b, val_b in nums_b:
            if ctx_a == ctx_b and val_a != val_b:
                return True
    return False


def _extract_numbers_with_context(text: str) -> list[tuple[str, str]]:
    """Extract (context_word, number_string) pairs."""
    pairs = []
    for m in _NUMBER_PATTERN.finditer(text):
        start = max(0, m.start() - 6)
        context = text[start:m.start()].strip()
        context = re.split(r"[，。！？；：、\s,.:;!?]+", context)[-1] if context else ""
        if context:
            pairs.append((context, m.group(0)))
    return pairs


# ── Memory vs document evidence conflict ──────────────────────────────


@dataclass(frozen=True)
class MemoryConflict:
    """A detected contradiction between a memory entry and document evidence."""

    memory_id: str
    memory_key: str
    memory_content: str
    conflicting_chunk_id: str
    conflict_type: str  # "negation" | "numeric"
    warning: str = "记忆可能陈旧或错误"


def detect_memory_evidence_conflicts(
    memories: list[tuple[str, str, str]],
    evidence_texts: dict[str, str],
) -> list[MemoryConflict]:
    """Detect conflicts between memory entries and document evidence.

    *memories* is a list of ``(memory_id, key, content)`` tuples.
    *evidence_texts* maps chunk_id → chunk text.

    Document evidence always wins — this function only identifies where
    they disagree so the caller can prompt the user.
    """
    conflicts: list[MemoryConflict] = []
    for memory_id, key, content in memories:
        for chunk_id, chunk_text in evidence_texts.items():
            if _has_negation_conflict(content, chunk_text):
                conflicts.append(MemoryConflict(
                    memory_id=memory_id,
                    memory_key=key,
                    memory_content=content,
                    conflicting_chunk_id=chunk_id,
                    conflict_type="negation",
                ))
            elif _has_numeric_conflict(content, chunk_text):
                conflicts.append(MemoryConflict(
                    memory_id=memory_id,
                    memory_key=key,
                    memory_content=content,
                    conflicting_chunk_id=chunk_id,
                    conflict_type="numeric",
                ))
    return conflicts

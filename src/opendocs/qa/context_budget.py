"""Context budget allocation and trimming for QA prompts.

Default ratios (spec FR-010):
  evidence  50%
  memory    20%
  instruct  10%
  user      20%

Trim order (low → high priority):
  1. low-importance memory
  2. duplicate / low-score evidence
  3. instructions and user input are never trimmed
"""

from __future__ import annotations

from dataclasses import dataclass, field


def _estimate_tokens(text: str) -> int:
    """Rough CJK-friendly token estimate (no tokenizer dependency)."""
    return max(1, len(text) // 2)


@dataclass(frozen=True)
class BudgetSlot:
    label: str
    ratio: float
    items: list[str]
    token_estimate: int


@dataclass(frozen=True)
class BudgetAllocation:
    slots: list[BudgetSlot]
    total_tokens: int
    trimmed_labels: list[str] = field(default_factory=list)


_RATIOS = {
    "evidence": 0.50,
    "memory": 0.20,
    "instructions": 0.10,
    "user_input": 0.20,
}


def allocate_budget(
    *,
    evidence_texts: list[str],
    memory_texts: list[str],
    instruction_text: str,
    user_input: str,
    max_tokens: int = 4096,
) -> BudgetAllocation:
    """Allocate context budget, trimming if over *max_tokens*."""
    raw: dict[str, list[str]] = {
        "evidence": list(evidence_texts),
        "memory": list(memory_texts),
        "instructions": [instruction_text],
        "user_input": [user_input],
    }

    slots = [
        BudgetSlot(
            label=label,
            ratio=_RATIOS[label],
            items=raw[label],
            token_estimate=sum(_estimate_tokens(t) for t in raw[label]),
        )
        for label in _RATIOS
    ]

    total = sum(s.token_estimate for s in slots)
    if total <= max_tokens:
        return BudgetAllocation(slots=slots, total_tokens=total)

    return _trim(slots, max_tokens)


def _trim(slots: list[BudgetSlot], max_tokens: int) -> BudgetAllocation:
    """Trim slots to fit *max_tokens*. Memory first, then evidence tail."""
    by_label = {s.label: s for s in slots}
    trimmed_labels: list[str] = []

    # Phase 1: trim memory (drop from tail = lowest importance first)
    mem = by_label["memory"]
    items = list(mem.items)
    while items and _total(by_label, trimmed_labels) > max_tokens:
        items.pop()
    if len(items) < len(mem.items):
        trimmed_labels.append("memory")
    by_label["memory"] = BudgetSlot(
        label="memory",
        ratio=mem.ratio,
        items=items,
        token_estimate=sum(_estimate_tokens(t) for t in items),
    )

    # Phase 2: trim evidence tail (keep at least first item)
    ev = by_label["evidence"]
    ev_items = list(ev.items)
    while len(ev_items) > 1 and _total(by_label, trimmed_labels) > max_tokens:
        ev_items.pop()
    if len(ev_items) < len(ev.items):
        if "evidence" not in trimmed_labels:
            trimmed_labels.append("evidence")
    by_label["evidence"] = BudgetSlot(
        label="evidence",
        ratio=ev.ratio,
        items=ev_items,
        token_estimate=sum(_estimate_tokens(t) for t in ev_items),
    )

    final = [by_label[label] for label in _RATIOS]
    return BudgetAllocation(
        slots=final,
        total_tokens=sum(s.token_estimate for s in final),
        trimmed_labels=trimmed_labels,
    )


def _total(
    by_label: dict[str, BudgetSlot],
    _trimmed: list[str],
) -> int:
    return sum(s.token_estimate for s in by_label.values())

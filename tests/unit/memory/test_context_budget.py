"""Tests for context budget allocation and trimming."""

from __future__ import annotations

from opendocs.qa.context_budget import allocate_budget


def test_allocate_within_budget() -> None:
    result = allocate_budget(
        evidence_texts=["短文"],
        memory_texts=["记忆"],
        instruction_text="指令",
        user_input="问题",
        max_tokens=9999,
    )
    assert result.total_tokens <= 9999
    assert result.trimmed_labels == []


def test_trim_memory_first() -> None:
    result = allocate_budget(
        evidence_texts=["e" * 100],
        memory_texts=["m" * 200, "m" * 200, "m" * 200],
        instruction_text="i" * 20,
        user_input="u" * 20,
        max_tokens=200,
    )
    assert "memory" in result.trimmed_labels
    memory_slot = next(s for s in result.slots if s.label == "memory")
    assert len(memory_slot.items) < 3


def test_evidence_keeps_at_least_one() -> None:
    result = allocate_budget(
        evidence_texts=["e" * 200, "e" * 200, "e" * 200],
        memory_texts=["m" * 200],
        instruction_text="i" * 20,
        user_input="u" * 20,
        max_tokens=50,
    )
    evidence_slot = next(s for s in result.slots if s.label == "evidence")
    assert len(evidence_slot.items) >= 1


def test_instructions_never_trimmed() -> None:
    instruction = "i" * 200
    result = allocate_budget(
        evidence_texts=["e" * 200],
        memory_texts=["m" * 200],
        instruction_text=instruction,
        user_input="u" * 20,
        max_tokens=50,
    )
    instr_slot = next(s for s in result.slots if s.label == "instructions")
    assert instr_slot.items == [instruction]

"""Tests for memory-vs-evidence conflict detection."""

from __future__ import annotations

from opendocs.qa.conflict_detector import detect_memory_evidence_conflicts


def test_negation_conflict() -> None:
    memories = [("m1", "status", "项目已完成交付")]
    evidence = {"c1": "项目未完成交付，仍在进行中"}
    conflicts = detect_memory_evidence_conflicts(memories, evidence)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "negation"
    assert conflicts[0].memory_id == "m1"
    assert conflicts[0].conflicting_chunk_id == "c1"
    assert conflicts[0].warning == "记忆可能陈旧或错误"


def test_numeric_conflict() -> None:
    memories = [("m2", "budget", "预算100万")]
    evidence = {"c2": "预算200万"}
    conflicts = detect_memory_evidence_conflicts(memories, evidence)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "numeric"


def test_no_conflict() -> None:
    memories = [("m3", "info", "会议在周一")]
    evidence = {"c3": "报告已提交"}
    conflicts = detect_memory_evidence_conflicts(memories, evidence)
    assert conflicts == []

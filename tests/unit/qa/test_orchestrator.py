"""Query-plan routing tests for S5 QA orchestration."""

from __future__ import annotations

from opendocs.qa.orchestrator import QAOrchestrator


def test_orchestrator_routes_fact_enumeration_without_falling_back_to_summary() -> None:
    orchestrator = QAOrchestrator()

    plan = orchestrator.build_plan("Atlas 有哪些发布时间？")

    assert plan.intent == "fact_list"
    assert plan.requested_fact_keys == ("publish_time",)


def test_orchestrator_keeps_insight_requests_on_summary_path() -> None:
    orchestrator = QAOrchestrator()

    plan = orchestrator.build_plan("Atlas 项目当前有哪些关键决策？")

    assert plan.intent == "summary"
    assert plan.requested_insight_kinds == ("decision",)


def test_orchestrator_subject_terms_keep_project_anchor_only() -> None:
    orchestrator = QAOrchestrator()

    plan = orchestrator.build_plan("Nebula 项目的负责人是谁？")

    assert plan.intent == "fact"
    assert plan.subject_terms == ("nebula",)

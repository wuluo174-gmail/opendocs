"""Service-layer guardrail tests for file operation execution."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from opendocs.app import FileOperationService
from opendocs.domain.models import AuditLogModel, FileOperationPlanModel
from opendocs.exceptions import FileOpFailedError, PlanNotApprovedError
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import AuditRepository, PlanRepository


def _draft_plan() -> FileOperationPlanModel:
    return FileOperationPlanModel(
        plan_id=str(uuid.uuid4()),
        operation_type="move",
        status="draft",
        item_count=1,
        risk_level="low",
        preview_json={"items": [{"source": "a.md", "target": "archive/a.md"}]},
    )


def test_execute_plan_requires_approved_status(engine: Engine) -> None:
    with Session(engine) as session:
        repository = PlanRepository(session)
        plan = _draft_plan()
        repository.create(plan)
        session.commit()

        service = FileOperationService(session)
        with pytest.raises(PlanNotApprovedError, match="approved"):
            service.execute_plan(
                plan.plan_id,
                actor="system",
                trace_id="trace-draft-execute",
            )

        refreshed = repository.get_by_id(plan.plan_id)
        assert refreshed is not None
        assert refreshed.status == "draft"
        assert session.scalars(select(AuditLogModel)).all() == []


def test_execute_plan_marks_executed_and_writes_audit(engine: Engine) -> None:
    with Session(engine) as session:
        repository = PlanRepository(session)
        plan = _draft_plan()
        repository.create(plan)
        session.commit()

        service = FileOperationService(session)
        approved = service.approve_plan(plan.plan_id)
        assert approved.status == "approved"
        assert approved.approved_at is not None

        executed, audit = service.execute_plan(
            plan.plan_id,
            actor="user",
            trace_id="trace-approved-execute",
            detail_json={"item_count": 1},
        )
        session.commit()

        assert executed.status == "executed"
        assert executed.executed_at is not None
        assert audit.operation == "move_execute"
        assert audit.target_type == "plan"
        assert audit.target_id == plan.plan_id

        stored_audit = session.get(AuditLogModel, audit.audit_id)
        assert stored_audit is not None
        assert stored_audit.trace_id == "trace-approved-execute"
        assert stored_audit.detail_json["item_count"] == 1
        assert stored_audit.detail_json["execution_mode"] == "simulated"
        assert stored_audit.detail_json["simulated"] is True


def test_approve_plan_requires_draft_status(engine: Engine) -> None:
    with Session(engine) as session:
        repository = PlanRepository(session)
        plan = _draft_plan()
        repository.create(plan)
        session.commit()

        service = FileOperationService(session)
        service.approve_plan(plan.plan_id)
        session.commit()

        with pytest.raises(PlanNotApprovedError, match="draft status"):
            service.approve_plan(plan.plan_id)


def test_execute_plan_without_executor_auto_simulates(engine: Engine) -> None:
    """When no executor is configured, execute_plan auto-enters simulation mode."""
    with Session(engine) as session:
        repository = PlanRepository(session)
        plan = _draft_plan()
        repository.create(plan)
        session.commit()

        service = FileOperationService(session)
        service.approve_plan(plan.plan_id)
        session.commit()

        executed, audit = service.execute_plan(
            plan.plan_id,
            actor="system",
            trace_id="trace-auto-simulate",
        )
        session.commit()

        assert executed.status == "executed"
        assert audit.detail_json["execution_mode"] == "simulated"
        assert audit.detail_json["simulated"] is True


def test_executed_plan_cannot_be_re_executed(engine: Engine) -> None:
    """An already-executed plan must be rejected if execute_plan is called again."""
    with Session(engine) as session:
        repository = PlanRepository(session)
        plan = _draft_plan()
        repository.create(plan)
        session.commit()

        service = FileOperationService(session)
        service.approve_plan(plan.plan_id)
        service.execute_plan(
            plan.plan_id,
            actor="system",
            trace_id="trace-first-execute",
        )
        session.commit()

        refreshed = repository.get_by_id(plan.plan_id)
        assert refreshed is not None
        assert refreshed.status == "executed"

        with pytest.raises(PlanNotApprovedError, match="approved"):
            service.execute_plan(
                plan.plan_id,
                actor="system",
                trace_id="trace-second-execute",
            )


def test_execute_plan_sets_failed_status_on_executor_error(engine: Engine) -> None:
    """If operation_executor raises, plan.status must be 'failed' and a failure audit written."""

    def bad_executor(plan: FileOperationPlanModel) -> None:
        raise RuntimeError("disk full")

    plan_id: str
    with Session(engine) as session:
        plan = _draft_plan()
        plan_id = plan.plan_id
        PlanRepository(session).create(plan)
        session.commit()

        service = FileOperationService(session, operation_executor=bad_executor)
        service.approve_plan(plan_id)
        session.commit()

        with pytest.raises(FileOpFailedError, match="disk full"):
            service.execute_plan(
                plan_id,
                actor="system",
                trace_id="trace-fail-executor",
            )
        session.commit()

    with Session(engine) as session:
        failed_plan = PlanRepository(session).get_by_id(plan_id)
        assert failed_plan is not None
        assert failed_plan.status == "failed"
        assert failed_plan.executed_at is not None  # records when the failure happened

        audits = AuditRepository(session).query(trace_id="trace-fail-executor")
        assert len(audits) == 1
        assert audits[0].result == "failure"
        assert "disk full" in audits[0].detail_json.get("exec_error", "")


def test_executor_error_persists_failure_state_across_session_scope_rollback(
    engine: Engine,
) -> None:
    """Failure audit must survive the default session_scope() rollback path."""

    def bad_executor(plan: FileOperationPlanModel) -> None:
        raise RuntimeError("disk full")

    plan = _draft_plan()
    with session_scope(engine) as session:
        PlanRepository(session).create(plan)

    with pytest.raises(FileOpFailedError, match="disk full"):
        with session_scope(engine) as session:
            service = FileOperationService(session, operation_executor=bad_executor)
            service.approve_plan(plan.plan_id)
            service.execute_plan(
                plan.plan_id,
                actor="system",
                trace_id="trace-session-scope-failure",
            )

    with Session(engine) as session:
        failed_plan = PlanRepository(session).get_by_id(plan.plan_id)
        assert failed_plan is not None
        assert failed_plan.status == "failed"
        assert failed_plan.executed_at is not None

        audits = AuditRepository(session).query(trace_id="trace-session-scope-failure")
        assert len(audits) == 1
        assert audits[0].result == "failure"
        assert "disk full" in audits[0].detail_json.get("exec_error", "")

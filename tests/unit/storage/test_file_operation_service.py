"""Service-layer guardrail tests for file operation execution."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from opendocs.app import FileOperationService
from opendocs.domain.models import AuditLogModel, FileOperationPlanModel
from opendocs.storage.repositories import PlanRepository


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
        with pytest.raises(PermissionError, match="approved"):
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
            simulate=True,
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

        with pytest.raises(PermissionError, match="draft status"):
            service.approve_plan(plan.plan_id)


def test_execute_plan_without_executor_is_blocked_by_default(engine: Engine) -> None:
    with Session(engine) as session:
        repository = PlanRepository(session)
        plan = _draft_plan()
        repository.create(plan)
        session.commit()

        service = FileOperationService(session)
        service.approve_plan(plan.plan_id)
        session.commit()

        with pytest.raises(RuntimeError, match="executor is not configured"):
            service.execute_plan(
                plan.plan_id,
                actor="system",
                trace_id="trace-blocked-no-executor",
            )

        refreshed = repository.get_by_id(plan.plan_id)
        assert refreshed is not None
        assert refreshed.status == "approved"
        assert refreshed.executed_at is None
        assert session.scalars(select(AuditLogModel)).all() == []

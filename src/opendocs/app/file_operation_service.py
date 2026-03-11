"""Service-layer guardrails for file operation plan execution."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from opendocs.domain.models import AuditLogModel, FileOperationPlanModel
from opendocs.exceptions import FileOpFailedError, OpenDocsError, PlanNotApprovedError
from opendocs.storage.repositories import AuditRepository, PlanRepository
from opendocs.utils.time import utcnow_naive

_ALLOWED_OPERATION_TYPES = {"move", "rename", "create"}


class FileOperationService:
    """Enforce S1 write-operation invariants with plan + audit pairing."""

    def __init__(
        self,
        session: Session,
        *,
        plans: PlanRepository | None = None,
        audits: AuditRepository | None = None,
        operation_executor: Callable[[FileOperationPlanModel], None] | None = None,
    ) -> None:
        self._session = session
        self._plans = plans or PlanRepository(session)
        self._audits = audits or AuditRepository(session)
        self._operation_executor = operation_executor

    def approve_plan(
        self,
        plan_id: str,
        *,
        approved_at: datetime | None = None,
    ) -> FileOperationPlanModel:
        plan = self._require_plan(plan_id)
        if plan.status != "draft":
            raise PlanNotApprovedError("plan must be in draft status before approval")
        self._plans.update_status(plan_id, "approved", approved_at=approved_at)
        return self._require_plan(plan_id)

    def execute_plan(
        self,
        plan_id: str,
        *,
        actor: str,
        trace_id: str,
        detail_json: dict[str, Any] | None = None,
        executed_at: datetime | None = None,
    ) -> tuple[FileOperationPlanModel, AuditLogModel]:
        plan = self._require_plan(plan_id)
        if plan.operation_type not in _ALLOWED_OPERATION_TYPES:
            raise PlanNotApprovedError("only move/rename/create plans can be executed")
        if plan.status != "approved":
            raise PlanNotApprovedError("plan must be approved before execution")

        if self._operation_executor is None:
            raise FileOpFailedError("operation executor is not configured")

        try:
            self._operation_executor(plan)
        except Exception as exc:
            fail_time = executed_at or utcnow_naive()
            self._persist_failure(
                plan=plan,
                actor=actor,
                trace_id=trace_id,
                detail_json=detail_json,
                fail_time=fail_time,
                exec_error=str(exc),
            )
            raise FileOpFailedError(str(exc)) from exc

        execute_time = executed_at or utcnow_naive()
        self._plans.update_status(plan_id, "executed", executed_at=execute_time, _internal=True)

        audit_detail = dict(detail_json or {})
        audit_detail["execution_mode"] = "real"

        audit = AuditLogModel(
            audit_id=str(uuid.uuid4()),
            timestamp=execute_time,
            actor=actor,
            operation=f"{plan.operation_type}_execute",
            target_type="plan",
            target_id=plan.plan_id,
            result="success",
            detail_json=audit_detail,
            trace_id=trace_id,
        )
        self._audits.create(audit)

        return self._require_plan(plan_id), audit

    def _require_plan(self, plan_id: str) -> FileOperationPlanModel:
        plan = self._plans.get_by_id(plan_id)
        if plan is None:
            raise OpenDocsError(f"plan not found: {plan_id}")
        return plan

    def _persist_failure(
        self,
        *,
        plan: FileOperationPlanModel,
        actor: str,
        trace_id: str,
        detail_json: dict[str, Any] | None,
        fail_time: datetime,
        exec_error: str,
    ) -> None:
        # Failure audit must survive the caller's default session_scope()
        # rollback, so persist it in a fresh transaction after rolling back
        # the current session.
        self._session.rollback()
        bind = self._resolve_engine()
        with Session(bind, expire_on_commit=False) as failure_session:
            failure_plans = PlanRepository(failure_session)
            failure_audits = AuditRepository(failure_session)
            failed_plan = failure_plans.get_by_id(plan.plan_id)
            if failed_plan is None:
                raise OpenDocsError(f"plan not found after rollback: {plan.plan_id}")

            failed_plan.status = "failed"
            failed_plan.executed_at = fail_time
            if failed_plan.approved_at is None and plan.approved_at is not None:
                failed_plan.approved_at = plan.approved_at

            failure_audits.create(
                AuditLogModel(
                    audit_id=str(uuid.uuid4()),
                    timestamp=fail_time,
                    actor=actor,
                    operation=f"{plan.operation_type}_execute",
                    target_type="plan",
                    target_id=plan.plan_id,
                    result="failure",
                    detail_json={**(detail_json or {}), "exec_error": exec_error},
                    trace_id=trace_id,
                )
            )
            failure_session.commit()

    def _resolve_engine(self) -> Engine:
        bind = self._session.get_bind()
        if bind is None:
            raise OpenDocsError("session is not bound to an engine")
        if isinstance(bind, Connection):
            return bind.engine
        return bind

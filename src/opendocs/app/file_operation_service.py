"""Service-layer guardrails for file operation plan execution."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Callable

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

        execution_mode = "real"
        if self._operation_executor is None:
            # No executor configured — auto-enter simulation mode (S1 baseline).
            execution_mode = "simulated"
        else:
            try:
                self._operation_executor(plan)
            except Exception as exc:
                fail_time = executed_at or utcnow_naive()
                self._plans.update_status(plan_id, "failed")
                fail_audit = AuditLogModel(
                    audit_id=str(uuid.uuid4()),
                    timestamp=fail_time,
                    actor=actor,
                    operation=f"{plan.operation_type}_execute",
                    target_type="plan",
                    target_id=plan.plan_id,
                    result="failure",
                    detail_json={**(detail_json or {}), "exec_error": str(exc)},
                    trace_id=trace_id,
                )
                self._audits.create(fail_audit)
                raise FileOpFailedError(str(exc)) from exc

        execute_time = executed_at or utcnow_naive()
        self._plans.update_status(plan_id, "executed", executed_at=execute_time, _internal=True)

        audit_detail = dict(detail_json or {})
        audit_detail["execution_mode"] = execution_mode
        audit_detail["simulated"] = execution_mode == "simulated"

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

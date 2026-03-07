"""Repository for file operation plan persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from opendocs.domain.models import FileOperationPlanModel
from opendocs.exceptions import DeleteNotAllowedError, PlanNotApprovedError
from opendocs.utils.time import utcnow_naive


class PlanRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, plan: FileOperationPlanModel) -> FileOperationPlanModel:
        self._session.add(plan)
        self._session.flush()
        return plan

    def get_by_id(self, plan_id: str) -> FileOperationPlanModel | None:
        return self._session.get(FileOperationPlanModel, plan_id)

    def list_by_status(self, status: str) -> list[FileOperationPlanModel]:
        statement = select(FileOperationPlanModel).where(FileOperationPlanModel.status == status)
        return list(self._session.scalars(statement))

    def update_status(
        self,
        plan_id: str,
        status: str,
        *,
        approved_at: datetime | None = None,
        executed_at: datetime | None = None,
        _internal: bool = False,
    ) -> bool:
        if status == "executed" and not _internal:
            raise PlanNotApprovedError(
                "executed status transition must use FileOperationService.execute_plan"
            )
        if executed_at is not None and not _internal:
            raise ValueError("executed_at is managed only by FileOperationService.execute_plan")
        plan = self.get_by_id(plan_id)
        if plan is None:
            return False
        plan.status = status
        if status == "approved":
            plan.approved_at = approved_at or utcnow_naive()
        if status == "executed":
            plan.executed_at = executed_at or utcnow_naive()
        if status == "failed":
            plan.executed_at = utcnow_naive()
        self._session.flush()
        return True

    def delete(self, plan_id: str, *, allow_delete: bool = False) -> bool:
        if not allow_delete:
            raise DeleteNotAllowedError(
                "delete is disabled by default; pass allow_delete=True explicitly"
            )
        plan = self.get_by_id(plan_id)
        if plan is None:
            return False
        self._session.delete(plan)
        self._session.flush()
        return True

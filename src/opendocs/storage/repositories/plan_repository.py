"""Repository for file operation plan persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from opendocs.domain.models import FileOperationPlanModel


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
    ) -> bool:
        plan = self.get_by_id(plan_id)
        if plan is None:
            return False
        plan.status = status
        if status == "approved":
            plan.approved_at = approved_at or datetime.now(UTC).replace(tzinfo=None)
        if status == "executed":
            plan.executed_at = executed_at or datetime.now(UTC).replace(tzinfo=None)
        self._session.flush()
        return True

    def delete(self, plan_id: str, *, allow_delete: bool = False) -> bool:
        if not allow_delete:
            raise PermissionError(
                "delete is disabled by default; pass allow_delete=True explicitly"
            )
        plan = self.get_by_id(plan_id)
        if plan is None:
            return False
        self._session.delete(plan)
        self._session.flush()
        return True

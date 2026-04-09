"""Repository for structured task event persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from opendocs.domain.models import TaskEventModel


class TaskEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, task_event: TaskEventModel) -> TaskEventModel:
        self._session.add(task_event)
        self._session.flush()
        return task_event

    def get_by_id(self, event_id: str) -> TaskEventModel | None:
        return self._session.get(TaskEventModel, event_id)

    def find_by_business_key(
        self,
        *,
        trace_id: str,
        stage_id: str,
        task_type: str,
        scope_type: str,
        scope_id: str,
    ) -> TaskEventModel | None:
        statement = (
            select(TaskEventModel)
            .where(
                TaskEventModel.trace_id == trace_id,
                TaskEventModel.stage_id == stage_id,
                TaskEventModel.task_type == task_type,
                TaskEventModel.scope_type == scope_type,
                TaskEventModel.scope_id == scope_id,
            )
            .order_by(TaskEventModel.persisted_at.desc(), TaskEventModel.occurred_at.desc())
            .limit(1)
        )
        return self._session.scalar(statement)

    def list_by_scope(
        self,
        *,
        scope_type: str,
        scope_id: str,
        limit: int | None = None,
    ) -> list[TaskEventModel]:
        statement = (
            select(TaskEventModel)
            .where(TaskEventModel.scope_type == scope_type, TaskEventModel.scope_id == scope_id)
            .order_by(TaskEventModel.occurred_at.desc(), TaskEventModel.persisted_at.desc())
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.scalars(statement))

    def list_by_trace(self, trace_id: str, *, limit: int | None = None) -> list[TaskEventModel]:
        statement = (
            select(TaskEventModel)
            .where(TaskEventModel.trace_id == trace_id)
            .order_by(TaskEventModel.persisted_at.desc(), TaskEventModel.occurred_at.desc())
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.scalars(statement))

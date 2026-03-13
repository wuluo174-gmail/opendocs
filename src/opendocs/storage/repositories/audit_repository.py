"""Repository for append-only audit log persistence and query."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opendocs.domain.models import AuditLogModel
from opendocs.exceptions import DeleteNotAllowedError


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, audit_log: AuditLogModel) -> AuditLogModel:
        self._session.add(audit_log)
        self._session.flush()
        return audit_log

    def get_by_id(self, audit_id: str) -> AuditLogModel | None:
        return self._session.get(AuditLogModel, audit_id)

    def update_detail(
        self,
        audit_id: str,
        *,
        detail_json: dict[str, object],
        result: str | None = None,
    ) -> bool:
        audit_log = self.get_by_id(audit_id)
        if audit_log is None:
            return False
        audit_log.detail_json = detail_json
        if result is not None:
            audit_log.result = result
        self._session.flush()
        return True

    def delete(self, audit_id: str, *, allow_delete: bool = False) -> bool:
        raise DeleteNotAllowedError(
            "audit log deletion is forbidden; audit records must remain append-only"
        )

    def query(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        task_id: str | None = None,
        trace_id: str | None = None,
        file_path: str | None = None,
        target_type: str | None = None,
        limit: int | None = 200,
    ) -> list[AuditLogModel]:
        statement = select(AuditLogModel)
        if start_time is not None:
            statement = statement.where(AuditLogModel.timestamp >= start_time)
        if end_time is not None:
            statement = statement.where(AuditLogModel.timestamp <= end_time)
        if task_id is not None:
            statement = statement.where(
                func.json_extract(AuditLogModel.detail_json, "$.task_id") == task_id
            )
        if trace_id is not None:
            statement = statement.where(AuditLogModel.trace_id == trace_id)
        if target_type is not None:
            statement = statement.where(AuditLogModel.target_type == target_type)
        if file_path is not None:
            statement = statement.where(
                func.json_extract(AuditLogModel.detail_json, "$.file_path") == file_path
            )

        statement = statement.order_by(AuditLogModel.timestamp.desc())
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.scalars(statement))

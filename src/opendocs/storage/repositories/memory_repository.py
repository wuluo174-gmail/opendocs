"""Repository for memory persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from opendocs.domain.models import MemoryItemModel, TaskEventModel
from opendocs.exceptions import DeleteNotAllowedError, StorageError
from opendocs.utils.time import utcnow_naive


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, memory_item: MemoryItemModel) -> MemoryItemModel:
        if memory_item.memory_type not in {"M1", "M2"}:
            raise StorageError("only M1/M2 memories may be persisted")
        if memory_item.scope_type == "session":
            raise StorageError("session-scoped memory must remain in M0 and stay in-process only")
        if not memory_item.source_event_ids_json:
            raise StorageError("persisted memory must reference at least one stored task event")

        missing_event_ids = [
            event_id
            for event_id in memory_item.source_event_ids_json
            if self._session.get(TaskEventModel, event_id) is None
        ]
        if missing_event_ids:
            missing_text = ", ".join(missing_event_ids)
            raise StorageError(
                "persisted memory must reference real task events before it can be stored: "
                f"{missing_text}"
            )

        self._session.add(memory_item)
        self._session.flush()
        return memory_item

    def get_by_id(self, memory_id: str) -> MemoryItemModel | None:
        return self._session.get(MemoryItemModel, memory_id)

    def get_by_scope_key(
        self,
        *,
        memory_type: str,
        scope_type: str,
        scope_id: str,
        key: str,
        include_inactive: bool = False,
    ) -> MemoryItemModel | None:
        statement = select(MemoryItemModel).where(
            MemoryItemModel.memory_type == memory_type,
            MemoryItemModel.scope_type == scope_type,
            MemoryItemModel.scope_id == scope_id,
            MemoryItemModel.key == key,
        )
        if not include_inactive:
            statement = statement.where(
                MemoryItemModel.status == "active",
                MemoryItemModel.promotion_state == "promoted",
            )
        statement = statement.order_by(MemoryItemModel.updated_at.desc()).limit(1)
        return self._session.scalar(statement)

    def list_active_by_scope(
        self,
        *,
        scope_type: str,
        scope_id: str,
        memory_type: str | None = None,
    ) -> list[MemoryItemModel]:
        statement = select(MemoryItemModel).where(
            MemoryItemModel.scope_type == scope_type,
            MemoryItemModel.scope_id == scope_id,
            MemoryItemModel.status == "active",
            MemoryItemModel.promotion_state == "promoted",
        )
        if memory_type is not None:
            statement = statement.where(MemoryItemModel.memory_type == memory_type)
        statement = statement.order_by(MemoryItemModel.importance.desc())
        return list(self._session.scalars(statement))

    def update_status(self, memory_id: str, status: str) -> bool:
        memory_item = self.get_by_id(memory_id)
        if memory_item is None:
            return False
        memory_item.status = status
        memory_item.updated_at = utcnow_naive()
        self._session.flush()
        return True

    def delete(self, memory_id: str, *, allow_delete: bool = False) -> bool:
        if not allow_delete:
            raise DeleteNotAllowedError(
                "delete is disabled by default; pass allow_delete=True explicitly"
            )
        memory_item = self.get_by_id(memory_id)
        if memory_item is None:
            return False
        self._session.delete(memory_item)
        self._session.flush()
        return True

"""Repository for memory persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from opendocs.domain.models import MemoryItemModel
from opendocs.exceptions import DeleteNotAllowedError
from opendocs.utils.time import utcnow_naive


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, memory_item: MemoryItemModel) -> MemoryItemModel:
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
    ) -> MemoryItemModel | None:
        statement = select(MemoryItemModel).where(
            MemoryItemModel.memory_type == memory_type,
            MemoryItemModel.scope_type == scope_type,
            MemoryItemModel.scope_id == scope_id,
            MemoryItemModel.key == key,
        )
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

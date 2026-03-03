"""Repository for memory persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from opendocs.domain.models import MemoryItemModel


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

    def update_status(self, memory_id: str, status: str) -> bool:
        memory_item = self.get_by_id(memory_id)
        if memory_item is None:
            return False
        memory_item.status = status
        memory_item.updated_at = datetime.now(UTC).replace(tzinfo=None)
        self._session.flush()
        return True

    def delete(self, memory_id: str) -> bool:
        memory_item = self.get_by_id(memory_id)
        if memory_item is None:
            return False
        self._session.delete(memory_item)
        self._session.flush()
        return True

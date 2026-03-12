"""Minimal memory service boundary for S1 storage baseline."""

from __future__ import annotations

from sqlalchemy.orm import Session

from opendocs.domain.models import MemoryItemModel
from opendocs.exceptions import StorageError
from opendocs.storage.repositories import MemoryRepository


class MemoryService:
    """Keep memory persistence policy out of the repository layer.

    S1 only needs the smallest boundary guard: M0 session memory is valid as a
    domain concept but must not be persisted. Broader TTL, promotion, and
    conflict management remain in S8.
    """

    def __init__(
        self,
        session: Session,
        *,
        memories: MemoryRepository | None = None,
    ) -> None:
        self._memories = memories or MemoryRepository(session)

    def create(self, memory_item: MemoryItemModel) -> MemoryItemModel:
        if memory_item.memory_type == "M0":
            raise StorageError("M0 session memory must not be persisted; store it in-process only")
        return self._memories.create(memory_item)

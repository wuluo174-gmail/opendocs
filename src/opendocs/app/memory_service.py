"""Minimal memory service boundary for S1 storage baseline."""

from __future__ import annotations

from sqlalchemy.orm import Session

from opendocs.domain.models import MemoryItemModel
from opendocs.exceptions import StorageError
from opendocs.storage.repositories import MemoryRepository


class MemoryService:
    """Keep memory persistence policy out of the repository layer.

    S1 only needs the smallest storage boundary guard: persisted memory must
    already be structured M1/M2 backed by stored task events. Runtime M0 and
    broader consolidation/promotion logic remain in S8.
    """

    def __init__(
        self,
        session: Session,
        *,
        memories: MemoryRepository | None = None,
    ) -> None:
        self._memories = memories or MemoryRepository(session)

    def create(self, memory_item: MemoryItemModel) -> MemoryItemModel:
        if memory_item.memory_type not in {"M1", "M2"}:
            raise StorageError("only M1/M2 memories may be persisted")
        if memory_item.scope_type == "session":
            raise StorageError("session-scoped memory must remain in M0 and stay in-process only")
        return self._memories.create(memory_item)

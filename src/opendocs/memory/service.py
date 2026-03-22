"""Full memory service — lifecycle, TTL, upgrade, management, audit."""

from __future__ import annotations

import uuid

from sqlalchemy.engine import Engine

from opendocs.app._audit_helpers import create_audit_record, flush_audit_to_jsonl
from opendocs.config.settings import MemorySettings
from opendocs.domain.models import MemoryItemModel
from opendocs.exceptions import StorageError
from opendocs.memory.policy import default_ttl, is_expired, m2_gate, should_upgrade_to_m2
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import MemoryRepository
from opendocs.utils.time import utcnow_naive

_ACTOR = "system"


class MemoryService:
    """Manage M0/M1/M2 lifecycle with TTL, upgrade, and audit."""

    def __init__(
        self,
        engine: Engine,
        *,
        settings: MemorySettings | None = None,
    ) -> None:
        self._engine = engine
        self._settings = settings or MemorySettings()

    # ── write / recall / get ──────────────────────────────────────────

    def write(
        self,
        *,
        memory_type: str,
        scope_type: str,
        scope_id: str,
        key: str,
        content: str,
        importance: float = 0.5,
        trace_id: str,
    ) -> MemoryItemModel:
        if memory_type == "M0":
            raise StorageError("M0 session memory must not be persisted")
        if memory_type == "M2":
            m2_gate(self._settings.m2_enabled)

        ttl = default_ttl(memory_type, self._settings.m1_ttl_days)

        with session_scope(self._engine) as session:
            repo = MemoryRepository(session)
            existing = repo.get_by_scope_key(
                memory_type=memory_type,
                scope_type=scope_type,
                scope_id=scope_id,
                key=key,
            )
            if existing and existing.status == "active":
                existing.content = content
                existing.importance = importance
                existing.confirmed_count += 1
                existing.last_confirmed_at = utcnow_naive()
                existing.updated_at = utcnow_naive()
                session.flush()
                item = existing
            else:
                item = MemoryItemModel(
                    memory_id=str(uuid.uuid4()),
                    memory_type=memory_type,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    key=key,
                    content=content,
                    importance=importance,
                    status="active",
                    ttl_days=ttl,
                    confirmed_count=0,
                )
                repo.create(item)

            audit = create_audit_record(
                session,
                actor=_ACTOR,
                operation="memory_write",
                target_type="memory",
                target_id=item.memory_id,
                result="success",
                detail_json={"memory_type": memory_type, "key": key},
                trace_id=trace_id,
            )

        flush_audit_to_jsonl(audit)
        return item

    def recall(
        self,
        *,
        scope_type: str,
        scope_id: str,
        memory_type: str | None = None,
    ) -> list[MemoryItemModel]:
        now = utcnow_naive()
        with session_scope(self._engine) as session:
            repo = MemoryRepository(session)
            items = repo.list_active_by_scope(
                scope_type=scope_type,
                scope_id=scope_id,
                memory_type=memory_type,
            )
            return [
                m for m in items
                if not is_expired(m.created_at, m.ttl_days, now)
            ]

    def get(self, memory_id: str) -> MemoryItemModel | None:
        with session_scope(self._engine) as session:
            return MemoryRepository(session).get_by_id(memory_id)

    # ── confirm / upgrade ─────────────────────────────────────────────

    def confirm(
        self,
        memory_id: str,
        *,
        trace_id: str,
        explicit_upgrade: bool = False,
    ) -> MemoryItemModel:
        with session_scope(self._engine) as session:
            repo = MemoryRepository(session)
            item = repo.get_by_id(memory_id)
            if item is None:
                raise StorageError(f"memory not found: {memory_id}")

            item.confirmed_count += 1
            item.last_confirmed_at = utcnow_naive()
            item.updated_at = utcnow_naive()

            if (
                item.memory_type == "M1"
                and should_upgrade_to_m2(item.confirmed_count, explicit_confirm=explicit_upgrade)
                and self._settings.m2_enabled
            ):
                item.memory_type = "M2"
                item.ttl_days = None

            session.flush()

            audit = create_audit_record(
                session,
                actor=_ACTOR,
                operation="memory_confirm",
                target_type="memory",
                target_id=memory_id,
                result="success",
                detail_json={
                    "confirmed_count": item.confirmed_count,
                    "memory_type": item.memory_type,
                },
                trace_id=trace_id,
            )

        flush_audit_to_jsonl(audit)
        return item

    # ── TTL cleanup ───────────────────────────────────────────────────

    def cleanup_expired(self, *, trace_id: str) -> int:
        with session_scope(self._engine) as session:
            repo = MemoryRepository(session)
            candidates = repo.list_expired_candidates(self._settings.m1_ttl_days)
            for item in candidates:
                item.status = "expired"
                item.updated_at = utcnow_naive()
            session.flush()

            if candidates:
                audit = create_audit_record(
                    session,
                    actor=_ACTOR,
                    operation="memory_expire",
                    target_type="memory",
                    target_id="batch",
                    result="success",
                    detail_json={"expired_count": len(candidates)},
                    trace_id=trace_id,
                )

        if candidates:
            flush_audit_to_jsonl(audit)
        return len(candidates)

    # ── management: disable / delete / correct ────────────────────────

    def disable(self, memory_id: str, *, trace_id: str) -> None:
        with session_scope(self._engine) as session:
            repo = MemoryRepository(session)
            if not repo.update_status(memory_id, "disabled"):
                raise StorageError(f"memory not found: {memory_id}")

            audit = create_audit_record(
                session,
                actor=_ACTOR,
                operation="memory_disable",
                target_type="memory",
                target_id=memory_id,
                result="success",
                trace_id=trace_id,
            )

        flush_audit_to_jsonl(audit)

    def delete(self, memory_id: str, *, trace_id: str) -> None:
        with session_scope(self._engine) as session:
            repo = MemoryRepository(session)
            if not repo.delete(memory_id, allow_delete=True):
                raise StorageError(f"memory not found: {memory_id}")

            audit = create_audit_record(
                session,
                actor=_ACTOR,
                operation="memory_delete",
                target_type="memory",
                target_id=memory_id,
                result="success",
                trace_id=trace_id,
            )

        flush_audit_to_jsonl(audit)

    def correct(
        self,
        memory_id: str,
        *,
        new_content: str,
        trace_id: str,
    ) -> MemoryItemModel:
        with session_scope(self._engine) as session:
            repo = MemoryRepository(session)
            item = repo.get_by_id(memory_id)
            if item is None:
                raise StorageError(f"memory not found: {memory_id}")

            old_content = item.content
            repo.update_content(memory_id, new_content)
            session.flush()

            # Re-fetch to get updated state
            item = repo.get_by_id(memory_id)

            audit = create_audit_record(
                session,
                actor=_ACTOR,
                operation="memory_correct",
                target_type="memory",
                target_id=memory_id,
                result="success",
                detail_json={
                    "old_content_length": len(old_content),
                    "new_content_length": len(new_content),
                },
                trace_id=trace_id,
            )

        flush_audit_to_jsonl(audit)
        return item  # type: ignore[return-value]

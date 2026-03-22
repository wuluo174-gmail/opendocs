"""TC-013: M1 task memory TTL lifecycle.

write → recall within TTL → expire → recall returns empty.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from opendocs.domain.models import AuditLogModel, MemoryItemModel
from opendocs.memory.service import MemoryService
from opendocs.utils.time import utcnow_naive


def test_m1_write_recall_expire_no_recall(
    memory_service: MemoryService,
    engine: Engine,
) -> None:
    trace = str(uuid.uuid4())

    # 1. Write M1 memory
    item = memory_service.write(
        memory_type="M1",
        scope_type="task",
        scope_id="task-001",
        key="progress",
        content="阶段一完成",
        trace_id=trace,
    )
    assert item.memory_type == "M1"
    assert item.status == "active"
    assert item.ttl_days == 30

    # 2. Recall within TTL — present
    recalled = memory_service.recall(scope_type="task", scope_id="task-001")
    assert len(recalled) == 1
    assert recalled[0].memory_id == item.memory_id

    # 3. Move created_at back 31 days to simulate TTL expiry
    with Session(engine) as session:
        row = session.get(MemoryItemModel, item.memory_id)
        assert row is not None
        row.created_at = utcnow_naive() - timedelta(days=31)
        session.commit()

    # 4. Recall after TTL — recall filters out expired
    recalled_after = memory_service.recall(scope_type="task", scope_id="task-001")
    assert recalled_after == []

    # 5. cleanup_expired materializes the expiry
    cleanup_trace = str(uuid.uuid4())
    expired_count = memory_service.cleanup_expired(trace_id=cleanup_trace)
    assert expired_count == 1

    # 6. Verify DB status is expired
    with Session(engine) as session:
        row = session.get(MemoryItemModel, item.memory_id)
        assert row is not None
        assert row.status == "expired"

    # 7. Audit trail exists
    with Session(engine) as session:
        audits = (
            session.query(AuditLogModel)
            .filter(AuditLogModel.operation == "memory_write")
            .all()
        )
        assert len(audits) >= 1

        expire_audits = (
            session.query(AuditLogModel)
            .filter(AuditLogModel.operation == "memory_expire")
            .all()
        )
        assert len(expire_audits) == 1


def test_m1_recall_does_not_return_disabled(
    memory_service: MemoryService,
    engine: Engine,
) -> None:
    trace = str(uuid.uuid4())

    item = memory_service.write(
        memory_type="M1",
        scope_type="task",
        scope_id="task-002",
        key="note",
        content="测试禁用",
        trace_id=trace,
    )

    memory_service.disable(item.memory_id, trace_id=trace)

    recalled = memory_service.recall(scope_type="task", scope_id="task-002")
    assert recalled == []

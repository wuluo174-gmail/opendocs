"""TC-014: Memory-evidence conflict detection, correction, and deletion.

conflict detected → correct/delete → old content no longer recalled.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from opendocs.domain.models import AuditLogModel
from opendocs.memory.service import MemoryService
from opendocs.qa.conflict_detector import detect_memory_evidence_conflicts


def test_conflict_detect_then_correct(
    memory_service: MemoryService,
    engine: Engine,
) -> None:
    trace = str(uuid.uuid4())

    # 1. Write memory with stale data
    item = memory_service.write(
        memory_type="M1",
        scope_type="task",
        scope_id="project-alpha",
        key="budget",
        content="预算100万",
        trace_id=trace,
    )

    # 2. Document evidence says otherwise
    evidence = {"chunk-99": "预算200万"}

    # 3. Detect conflict
    conflicts = detect_memory_evidence_conflicts(
        [(item.memory_id, "budget", item.content)],
        evidence,
    )
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "numeric"
    assert conflicts[0].warning == "记忆可能陈旧或错误"

    # 4. Correct the memory
    corrected = memory_service.correct(
        item.memory_id,
        new_content="预算200万",
        trace_id=trace,
    )
    assert corrected.content == "预算200万"

    # 5. Re-detect — no conflict
    conflicts_after = detect_memory_evidence_conflicts(
        [(corrected.memory_id, "budget", corrected.content)],
        evidence,
    )
    assert conflicts_after == []

    # 6. Audit trail for correction
    with Session(engine) as session:
        correct_audits = (
            session.query(AuditLogModel)
            .filter(AuditLogModel.operation == "memory_correct")
            .all()
        )
        assert len(correct_audits) == 1


def test_conflict_detect_then_delete(
    memory_service: MemoryService,
    engine: Engine,
) -> None:
    trace = str(uuid.uuid4())

    item = memory_service.write(
        memory_type="M1",
        scope_type="task",
        scope_id="project-beta",
        key="status",
        content="项目已完成交付",
        trace_id=trace,
    )

    evidence = {"chunk-100": "项目未完成交付，仍在进行中"}

    conflicts = detect_memory_evidence_conflicts(
        [(item.memory_id, "status", item.content)],
        evidence,
    )
    assert len(conflicts) >= 1

    # Delete the conflicting memory
    memory_service.delete(item.memory_id, trace_id=trace)

    # Recall returns empty
    recalled = memory_service.recall(
        scope_type="task",
        scope_id="project-beta",
    )
    assert recalled == []

    # get also returns None (physically deleted)
    assert memory_service.get(item.memory_id) is None


def test_m2_disabled_by_default(
    memory_service: MemoryService,
) -> None:
    """M2 writes are blocked when m2_enabled=False (default)."""
    import pytest
    from opendocs.exceptions import StorageError

    with pytest.raises(StorageError, match="M2 user preference memory is disabled"):
        memory_service.write(
            memory_type="M2",
            scope_type="user",
            scope_id="user-001",
            key="pref",
            content="偏好深色模式",
            trace_id=str(uuid.uuid4()),
        )

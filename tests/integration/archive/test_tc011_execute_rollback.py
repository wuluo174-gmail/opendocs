"""TC-011: Archive execute + rollback — files move then restore."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from sqlalchemy.engine import Engine

from opendocs.app.archive_service import ArchiveService
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import AuditRepository, PlanRepository


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_execute_moves_files(
    archive_service: ArchiveService,
    engine: Engine,
    seeded_docs: list[str],
    archive_dir: Path,
    source_files: list[Path],
) -> None:
    plan_id = archive_service.classify_and_plan(
        seeded_docs, base_archive_dir=str(archive_dir)
    )
    archive_service.approve(plan_id)
    archive_service.execute(plan_id)

    for f in source_files:
        assert not f.exists(), f"source file should be moved: {f}"

    with session_scope(engine) as session:
        plan = PlanRepository(session).get_by_id(plan_id)
        assert plan is not None
        assert plan.status == "executed"
        for item in plan.preview_json["items"]:
            assert os.path.exists(item["target_path"])


def test_execute_creates_audit(
    archive_service: ArchiveService,
    engine: Engine,
    seeded_docs: list[str],
    archive_dir: Path,
) -> None:
    plan_id = archive_service.classify_and_plan(
        seeded_docs, base_archive_dir=str(archive_dir)
    )
    archive_service.approve(plan_id)
    archive_service.execute(plan_id)

    with session_scope(engine) as session:
        audits = AuditRepository(session).query(target_type="plan")
        ops = {a.operation for a in audits if a.target_id == plan_id}
        assert "move_execute" in ops


def test_rollback_restores_files(
    archive_service: ArchiveService,
    engine: Engine,
    seeded_docs: list[str],
    archive_dir: Path,
    source_files: list[Path],
) -> None:
    original_hashes = {str(f.resolve()): _sha256(f) for f in source_files}

    plan_id = archive_service.classify_and_plan(
        seeded_docs, base_archive_dir=str(archive_dir)
    )
    archive_service.approve(plan_id)
    archive_service.execute(plan_id)

    items = archive_service.rollback_last_batch()
    assert all(i.restored for i in items)

    for f in source_files:
        assert f.exists(), f"source file should be restored: {f}"
        assert _sha256(f) == original_hashes[str(f.resolve())]

    with session_scope(engine) as session:
        plan = PlanRepository(session).get_by_id(plan_id)
        assert plan is not None
        assert plan.status == "rolled_back"


def test_rollback_audit_record(
    archive_service: ArchiveService,
    engine: Engine,
    seeded_docs: list[str],
    archive_dir: Path,
) -> None:
    plan_id = archive_service.classify_and_plan(
        seeded_docs, base_archive_dir=str(archive_dir)
    )
    archive_service.approve(plan_id)
    archive_service.execute(plan_id)
    archive_service.rollback_last_batch()

    with session_scope(engine) as session:
        audits = AuditRepository(session).query(target_type="rollback")
        matching = [a for a in audits if a.target_id == plan_id]
        assert len(matching) == 1
        assert matching[0].operation == "rollback_execute"
        assert matching[0].result == "success"

"""TC-010: Archive preview does not execute — cancel after preview means zero writes."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opendocs.app.archive_service import ArchiveService
from opendocs.domain.models import FileOperationPlanModel
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import PlanRepository


def test_draft_plan_has_items(
    archive_service: ArchiveService,
    engine: Engine,
    seeded_docs: list[str],
    archive_dir: Path,
    source_files: list[Path],
) -> None:
    plan_id = archive_service.classify_and_plan(
        seeded_docs, base_archive_dir=str(archive_dir)
    )

    with session_scope(engine) as session:
        plan = PlanRepository(session).get_by_id(plan_id)
        assert plan is not None
        assert plan.status == "draft"
        assert plan.item_count == len(seeded_docs)
        items = plan.preview_json["items"]
        assert len(items) == len(seeded_docs)

    for f in source_files:
        assert f.exists(), f"source file should still exist: {f}"


def test_no_target_files_after_draft(
    archive_service: ArchiveService,
    engine: Engine,
    seeded_docs: list[str],
    archive_dir: Path,
) -> None:
    plan_id = archive_service.classify_and_plan(
        seeded_docs, base_archive_dir=str(archive_dir)
    )

    with session_scope(engine) as session:
        plan = PlanRepository(session).get_by_id(plan_id)
        assert plan is not None
        for item in plan.preview_json["items"]:
            assert not os.path.exists(item["target_path"]), (
                f"target should not exist: {item['target_path']}"
            )


def test_preview_contains_classification_trace(
    archive_service: ArchiveService,
    engine: Engine,
    seeded_docs: list[str],
    archive_dir: Path,
) -> None:
    plan_id = archive_service.classify_and_plan(
        seeded_docs, base_archive_dir=str(archive_dir)
    )

    with session_scope(engine) as session:
        plan = PlanRepository(session).get_by_id(plan_id)
        assert plan is not None
        trace = plan.preview_json.get("classification_trace")
        assert trace is not None
        assert trace["strategy"] == "rule_based"


def test_audit_record_created_for_plan(
    archive_service: ArchiveService,
    engine: Engine,
    seeded_docs: list[str],
    archive_dir: Path,
) -> None:
    plan_id = archive_service.classify_and_plan(
        seeded_docs, base_archive_dir=str(archive_dir)
    )

    with session_scope(engine) as session:
        from opendocs.storage.repositories import AuditRepository
        audits = AuditRepository(session).query(target_type="plan")
        matching = [a for a in audits if a.target_id == plan_id]
        assert len(matching) == 1
        assert matching[0].operation == "archive_plan"

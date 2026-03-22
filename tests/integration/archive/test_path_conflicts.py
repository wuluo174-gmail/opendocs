"""Path conflict protection — no silent overwrite."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from opendocs.app.archive_service import ArchiveService
from opendocs.exceptions import FileOpFailedError
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import PlanRepository


def test_conflict_flagged_in_preview(
    archive_service: ArchiveService,
    engine: Engine,
    seeded_docs: list[str],
    archive_dir: Path,
    source_files: list[Path],
) -> None:
    """Pre-existing file at target → conflict=True in preview."""
    conflict_dir = archive_dir / "project-alpha"
    conflict_dir.mkdir(parents=True)
    (conflict_dir / source_files[0].name).write_text("occupied")

    plan_id = archive_service.classify_and_plan(
        seeded_docs, base_archive_dir=str(archive_dir)
    )

    with session_scope(engine) as session:
        plan = PlanRepository(session).get_by_id(plan_id)
        assert plan is not None
        assert plan.risk_level == "high"
        conflicts = [i for i in plan.preview_json["items"] if i["conflict"]]
        assert len(conflicts) >= 1


def test_execute_refuses_on_conflict(
    archive_service: ArchiveService,
    engine: Engine,
    seeded_docs: list[str],
    archive_dir: Path,
    source_files: list[Path],
) -> None:
    """Execute must fail if any item has conflict=True."""
    conflict_dir = archive_dir / "project-alpha"
    conflict_dir.mkdir(parents=True)
    (conflict_dir / source_files[0].name).write_text("occupied")

    plan_id = archive_service.classify_and_plan(
        seeded_docs, base_archive_dir=str(archive_dir)
    )
    archive_service.approve(plan_id)

    with pytest.raises(FileOpFailedError, match="conflict"):
        archive_service.execute(plan_id)

    for f in source_files:
        assert f.exists(), f"source file must not be moved on conflict: {f}"


def test_runtime_conflict_also_blocked(
    archive_service: ArchiveService,
    engine: Engine,
    seeded_docs: list[str],
    archive_dir: Path,
    source_files: list[Path],
) -> None:
    """Even if plan had no conflict, a file appearing at target before execute blocks it."""
    plan_id = archive_service.classify_and_plan(
        seeded_docs, base_archive_dir=str(archive_dir)
    )
    archive_service.approve(plan_id)

    with session_scope(engine) as session:
        plan = PlanRepository(session).get_by_id(plan_id)
        assert plan is not None
        first_target = plan.preview_json["items"][0]["target_path"]

    os.makedirs(os.path.dirname(first_target), exist_ok=True)
    Path(first_target).write_text("appeared after planning")

    with pytest.raises(FileOpFailedError, match="target already exists"):
        archive_service.execute(plan_id)

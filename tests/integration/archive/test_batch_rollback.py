"""Batch rollback — including partial failure scenarios."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from opendocs.app.archive_service import ArchiveService
from opendocs.exceptions import OpenDocsError, RollbackPartialError
from opendocs.storage.db import session_scope
from opendocs.storage.repositories import PlanRepository


def test_partial_rollback_raises(
    archive_service: ArchiveService,
    engine: Engine,
    seeded_docs: list[str],
    archive_dir: Path,
    source_files: list[Path],
) -> None:
    """Delete one moved file → rollback raises RollbackPartialError."""
    plan_id = archive_service.classify_and_plan(
        seeded_docs, base_archive_dir=str(archive_dir)
    )
    archive_service.approve(plan_id)
    archive_service.execute(plan_id)

    with session_scope(engine) as session:
        plan = PlanRepository(session).get_by_id(plan_id)
        assert plan is not None
        first_target = plan.preview_json["items"][0]["target_path"]

    os.remove(first_target)

    with pytest.raises(RollbackPartialError):
        archive_service.rollback_last_batch()


def test_partial_rollback_restores_remaining(
    archive_service: ArchiveService,
    engine: Engine,
    seeded_docs: list[str],
    archive_dir: Path,
    source_files: list[Path],
) -> None:
    """Even with partial failure, the other files get restored."""
    plan_id = archive_service.classify_and_plan(
        seeded_docs, base_archive_dir=str(archive_dir)
    )
    archive_service.approve(plan_id)
    archive_service.execute(plan_id)

    with session_scope(engine) as session:
        plan = PlanRepository(session).get_by_id(plan_id)
        assert plan is not None
        victim = plan.preview_json["items"][0]
        victim_target = victim["target_path"]
        victim_source = Path(victim["source_path"])

    os.remove(victim_target)

    try:
        archive_service.rollback_last_batch()
    except RollbackPartialError:
        pass

    source_set = {f.resolve() for f in source_files}
    for f in source_files:
        if f.resolve() == victim_source.resolve():
            assert not f.exists(), "deleted file cannot be restored"
        else:
            assert f.exists(), f"file should be restored: {f}"


def test_no_executed_plan_raises(
    archive_service: ArchiveService,
) -> None:
    with pytest.raises(OpenDocsError, match="no executed plan"):
        archive_service.rollback_last_batch()

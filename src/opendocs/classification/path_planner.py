"""S6-T02: Target path planner for archive operations."""

from __future__ import annotations

import os
from pathlib import Path

from opendocs.classification.models import ClassificationResult, PlannedMove


class PathPlanner:
    """Generate target paths from classification results. No physical I/O."""

    def __init__(self, base_archive_dir: str) -> None:
        self._base = str(Path(base_archive_dir).resolve())

    def plan(
        self,
        classifications: list[ClassificationResult],
        *,
        hashes: dict[str, str | None] | None = None,
    ) -> list[PlannedMove]:
        hashes = hashes or {}
        return [self._plan_one(c, hashes.get(c.doc_id)) for c in classifications]

    def _plan_one(
        self, cr: ClassificationResult, hash_sha256: str | None
    ) -> PlannedMove:
        category_dir = cr.category or "uncategorized"
        filename = Path(cr.current_path).name
        target = str(Path(self._base) / category_dir / filename)
        conflict = os.path.exists(target)
        return PlannedMove(
            doc_id=cr.doc_id,
            source_path=str(Path(cr.current_path).resolve()),
            target_path=target,
            operation_type="move",
            hash_sha256=hash_sha256,
            conflict=conflict,
        )

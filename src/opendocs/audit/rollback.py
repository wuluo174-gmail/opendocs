"""S6-T04: Rollback audit detail builder."""

from __future__ import annotations

from typing import Any

from opendocs.classification.models import RollbackItem


def build_rollback_audit_detail(
    plan_id: str,
    items: list[RollbackItem],
) -> dict[str, Any]:
    """Build detail_json for a rollback audit record."""
    failed = [i for i in items if not i.restored]
    return {
        "plan_id": plan_id,
        "restored_count": sum(1 for i in items if i.restored),
        "failed_count": len(failed),
        "failed_items": [
            {"doc_id": i.doc_id, "original_path": i.original_path, "error": i.error}
            for i in failed
        ],
    }

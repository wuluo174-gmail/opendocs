"""S6 data models for classification, archive planning, and rollback."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ClassificationResult(BaseModel):
    """Output of the rule-based classifier for a single document."""

    doc_id: str
    current_path: str
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class PlannedMove(BaseModel):
    """A single planned file operation within an archive plan."""

    doc_id: str
    source_path: str
    target_path: str
    operation_type: Literal["move", "rename"] = "move"
    hash_sha256: str | None = None
    conflict: bool = False


class RollbackItem(BaseModel):
    """Result of rolling back a single file operation."""

    doc_id: str
    original_path: str
    current_path: str
    restored: bool
    error: str | None = None

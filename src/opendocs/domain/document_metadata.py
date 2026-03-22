"""Canonical document metadata for source defaults and parsed documents."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SensitivityLevel = Literal["public", "internal", "sensitive"]

_SENSITIVITY_RANK: dict[SensitivityLevel, int] = {
    "public": 0,
    "internal": 1,
    "sensitive": 2,
}


def _normalize_token(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split()).lower()
    return text or None


class DocumentMetadata(BaseModel):
    """Normalized metadata carried by a document or source root."""

    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    sensitivity: SensitivityLevel | None = None

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, value: object) -> str | None:
        return _normalize_token(value)

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, value: object) -> list[object]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, Iterable):
            return list(value)
        raise TypeError("tags must be a string or iterable of strings")

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, values: list[object]) -> list[str]:
        seen: set[str] = set()
        tags: list[str] = []
        for value in values:
            normalized = _normalize_token(value)
            if normalized is None or normalized in seen:
                continue
            seen.add(normalized)
            tags.append(normalized)
        return tags

    @field_validator("sensitivity", mode="before")
    @classmethod
    def _normalize_sensitivity(cls, value: object) -> str | None:
        return _normalize_token(value)

    def normalized_with(self, normalizer: Callable[[str], str]) -> "DocumentMetadata":
        """Apply text normalization without changing ownership semantics."""
        return DocumentMetadata(
            category=normalizer(self.category) if self.category else None,
            tags=[normalizer(tag) for tag in self.tags],
            sensitivity=self.sensitivity,
        )

    def to_source_defaults(self) -> dict[str, object]:
        """Map metadata to SourceRootModel column names."""
        return {
            "default_category": self.category,
            "default_tags_json": list(self.tags),
            "default_sensitivity": self.sensitivity,
        }


def most_restrictive_sensitivity(*levels: SensitivityLevel | None) -> SensitivityLevel | None:
    candidates = [level for level in levels if level is not None]
    if not candidates:
        return None
    return max(candidates, key=_SENSITIVITY_RANK.__getitem__)


def merge_document_metadata(
    *,
    source_defaults: DocumentMetadata | None = None,
    declared: DocumentMetadata | None = None,
) -> DocumentMetadata:
    """Merge source defaults with document-declared metadata.

    Rules:
    - category: document value overrides source default
    - tags: union of source defaults and document tags
    - sensitivity: most restrictive level wins
    """

    source_defaults = source_defaults or DocumentMetadata()
    declared = declared or DocumentMetadata()
    return DocumentMetadata(
        category=declared.category or source_defaults.category,
        tags=[*source_defaults.tags, *declared.tags],
        sensitivity=most_restrictive_sensitivity(
            source_defaults.sensitivity,
            declared.sensitivity,
        ),
    )

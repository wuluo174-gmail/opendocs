"""Canonical locator value objects shared across indexing and retrieval."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParagraphRange:
    """Machine paragraph bounds stored as zero-based indices.

    Storage and internal processing keep zero-based bounds because they come
    directly from parser/chunker paragraph indices. User-facing displays must
    always convert them to one-based paragraph numbers.
    """

    start_zero: int
    end_zero: int

    def __post_init__(self) -> None:
        if self.start_zero < 0:
            raise ValueError(f"start_zero must be >= 0, got {self.start_zero}")
        if self.end_zero < self.start_zero:
            raise ValueError(
                f"end_zero ({self.end_zero}) must be >= start_zero ({self.start_zero})"
            )

    @classmethod
    def from_storage(
        cls,
        paragraph_start: int | None,
        paragraph_end: int | None,
    ) -> ParagraphRange | None:
        if paragraph_start is None and paragraph_end is None:
            return None

        if paragraph_start is None:
            paragraph_start = paragraph_end
        if paragraph_end is None:
            paragraph_end = paragraph_start

        assert paragraph_start is not None
        assert paragraph_end is not None
        return cls(paragraph_start, paragraph_end)

    @property
    def start_display(self) -> int:
        return self.start_zero + 1

    @property
    def end_display(self) -> int:
        return self.end_zero + 1

    def to_display_range(self) -> str:
        if self.start_display == self.end_display:
            return str(self.start_display)
        return f"{self.start_display}-{self.end_display}"


@dataclass(frozen=True)
class CharRange:
    """Machine character bounds stored as zero-based [start, end) offsets."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError(f"start must be >= 0, got {self.start}")
        if self.end < self.start:
            raise ValueError(f"end ({self.end}) must be >= start ({self.start})")

    @classmethod
    def parse(cls, value: str) -> CharRange:
        parts = value.split("-", maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"invalid char range: {value}")
        return cls(start=int(parts[0]), end=int(parts[1]))

    def to_display_range(self) -> str:
        return f"{self.start}-{self.end}"

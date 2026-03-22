"""Memory lifecycle rules — pure functions, zero I/O."""

from __future__ import annotations

from datetime import datetime

from opendocs.exceptions import StorageError


def is_expired(created_at: datetime, ttl_days: int | None, now: datetime) -> bool:
    """Return True when the memory has outlived its TTL.

    *ttl_days=None* means "never expires".
    """
    if ttl_days is None:
        return False
    return (now - created_at).days >= ttl_days


def should_upgrade_to_m2(confirmed_count: int, *, explicit_confirm: bool) -> bool:
    """M1 → M2 promotion gate: explicit confirm once OR frequency >= 3."""
    return explicit_confirm or confirmed_count >= 3


def m2_gate(m2_enabled: bool) -> None:
    """Raise if M2 writes are disabled."""
    if not m2_enabled:
        raise StorageError(
            "M2 user preference memory is disabled; enable via settings.memory.m2_enabled"
        )


def default_ttl(memory_type: str, m1_ttl_days: int) -> int | None:
    """Return the default TTL for *memory_type*. M2 never expires."""
    if memory_type == "M1":
        return m1_ttl_days
    if memory_type == "M2":
        return None
    raise StorageError(f"M0 must not be persisted, got memory_type={memory_type}")

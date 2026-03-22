"""Tests for memory lifecycle policy — pure functions."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from opendocs.exceptions import StorageError
from opendocs.memory.policy import default_ttl, is_expired, m2_gate, should_upgrade_to_m2

_NOW = datetime(2026, 3, 22, 12, 0, 0)


# ── is_expired ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("days_ago", "ttl_days", "expected"),
    [
        (25, 30, False),   # within TTL
        (30, 30, True),    # exact boundary
        (31, 30, True),    # past TTL
        (999, None, False),  # no TTL = never expires
        (0, 30, False),    # just created
    ],
    ids=["within", "boundary", "past", "no_ttl", "just_created"],
)
def test_is_expired(days_ago: int, ttl_days: int | None, expected: bool) -> None:
    created = _NOW - timedelta(days=days_ago)
    assert is_expired(created, ttl_days, _NOW) is expected


# ── should_upgrade_to_m2 ─────────────────────────────────────────────

@pytest.mark.parametrize(
    ("count", "explicit", "expected"),
    [
        (0, True, True),    # explicit confirm alone
        (3, False, True),   # frequency threshold
        (5, False, True),   # above threshold
        (2, False, False),  # below threshold, no confirm
        (0, False, False),  # nothing
    ],
    ids=["explicit", "freq_3", "freq_5", "below_threshold", "nothing"],
)
def test_should_upgrade_to_m2(count: int, explicit: bool, expected: bool) -> None:
    assert should_upgrade_to_m2(count, explicit_confirm=explicit) is expected


# ── m2_gate ───────────────────────────────────────────────────────────

def test_m2_gate_disabled_raises() -> None:
    with pytest.raises(StorageError, match="M2 user preference memory is disabled"):
        m2_gate(False)


def test_m2_gate_enabled_passes() -> None:
    m2_gate(True)  # no exception


# ── default_ttl ───────────────────────────────────────────────────────

def test_default_ttl_m1() -> None:
    assert default_ttl("M1", 30) == 30


def test_default_ttl_m2() -> None:
    assert default_ttl("M2", 30) is None


def test_default_ttl_m0_raises() -> None:
    with pytest.raises(StorageError, match="M0 must not be persisted"):
        default_ttl("M0", 30)

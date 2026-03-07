"""Time utilities."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow_naive() -> datetime:
    """Return current UTC time as a timezone-naive datetime (for SQLite storage).

    Microseconds are truncated to align with SQLite's ``datetime('now')``
    which produces ``YYYY-MM-DD HH:MM:SS`` (no fractional seconds).
    See ADR-0003 "时间格式约定" for details.
    """
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)

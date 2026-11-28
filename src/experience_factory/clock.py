"""Where the core reads the current time."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

type Clock = Callable[[], datetime]
"""Where the core reads the current time: a timezone-aware datetime."""


def utc_now() -> datetime:
    """The current time in UTC, the clock the core reads in operation."""
    return datetime.now(UTC)

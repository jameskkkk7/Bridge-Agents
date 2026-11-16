"""Small shared helpers used across the application."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4


def new_uuid() -> str:
    """Return a new lower-case, dashed UUID string."""
    return str(uuid4())


def utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)

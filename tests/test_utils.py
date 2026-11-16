"""Tests for the small shared helpers."""

from __future__ import annotations

from datetime import UTC
from uuid import UUID

from app.core.utils import new_uuid, utcnow


def test_new_uuid_returns_dashed_uuid_string() -> None:
    value = new_uuid()
    assert isinstance(value, str)
    assert str(UUID(value)) == value
    assert UUID(value).version == 4


def test_new_uuid_is_unique() -> None:
    assert len({new_uuid() for _ in range(200)}) == 200


def test_utcnow_is_timezone_aware_utc() -> None:
    now = utcnow()
    assert now.tzinfo is not None
    assert now.utcoffset() == UTC.utcoffset(None)

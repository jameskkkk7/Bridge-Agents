"""Declarative base and shared column mixins."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.utils import new_uuid


def utc_timestamp() -> datetime:
    """Naive UTC timestamp for database columns (SQLite has no timezone type)."""
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class IdMixin:
    """Primary key stored as a lower-case, dashed UUID string."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)


class TimestampMixin:
    """Creation and last-update timestamps in UTC."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_timestamp, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_timestamp, onupdate=utc_timestamp, nullable=False
    )


class BaseModel(IdMixin, TimestampMixin, Base):
    """Abstract base with a string UUID primary key and timestamps."""

    __abstract__ = True

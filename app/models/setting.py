"""Runtime settings persisted as JSON key/value pairs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_timestamp


class Setting(Base):
    """A single runtime setting identified by an application-level key."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_timestamp, onupdate=utc_timestamp, nullable=False
    )

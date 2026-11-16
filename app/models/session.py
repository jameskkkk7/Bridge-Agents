"""Conversation session model."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.channel import SessionChannel
    from app.models.image import Image
    from app.models.message import Message
    from app.models.user import User


class SessionStatus(enum.StrEnum):
    """Lifecycle state of a conversation."""

    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


def _status_values(enum_class: type[enum.Enum]) -> list[str]:
    return [str(member.value) for member in enum_class]


class Session(BaseModel):
    """One conversation between a customer and the support runtime."""

    __tablename__ = "sessions"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), default="New conversation", nullable=False)
    status: Mapped[SessionStatus] = mapped_column(
        Enum(
            SessionStatus,
            native_enum=False,
            length=16,
            values_callable=_status_values,
        ),
        default=SessionStatus.ACTIVE,
        nullable=False,
    )
    human_takeover: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")
    messages: Mapped[list[Message]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    images: Mapped[list[Image]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    channels: Mapped[list[SessionChannel]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

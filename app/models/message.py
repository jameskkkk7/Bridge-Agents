"""Chat message model."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.session import Session


class SenderType(enum.StrEnum):
    """Who produced a message."""

    USER = "user"
    AGENT = "agent"


class MessageType(enum.StrEnum):
    """Rendering kind of a message."""

    TEXT = "text"
    SYSTEM = "system"
    IMAGE = "image"


def _enum_values(enum_class: type[enum.Enum]) -> list[str]:
    return [str(member.value) for member in enum_class]


class Message(BaseModel):
    """A single message inside a conversation."""

    __tablename__ = "messages"

    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sender_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    sender_type: Mapped[SenderType] = mapped_column(
        Enum(SenderType, native_enum=False, length=16, values_callable=_enum_values),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[MessageType] = mapped_column(
        Enum(MessageType, native_enum=False, length=16, values_callable=_enum_values),
        default=MessageType.TEXT,
        nullable=False,
    )

    session: Mapped[Session] = relationship(back_populates="messages")

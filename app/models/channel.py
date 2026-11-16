"""Session to external channel mapping.

A session may be mirrored into an external chat (for example a Lark group).
Each channel keeps at most one external thread per session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.session import Session


class SessionChannel(BaseModel):
    """Mapping between a session and one external channel conversation."""

    __tablename__ = "session_channels"
    __table_args__ = (
        UniqueConstraint("session_id", "channel", name="uq_session_channels_session_channel"),
    )

    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    session: Mapped[Session] = relationship(back_populates="channels")

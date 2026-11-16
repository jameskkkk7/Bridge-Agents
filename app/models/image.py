"""Uploaded image metadata model.

The binary payload lives on disk under ``STORAGE_DIR``; only
the relative storage path is persisted here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.session import Session


class Image(BaseModel):
    """An image attached to a conversation."""

    __tablename__ = "images"

    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sender_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    image_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    session: Mapped[Session] = relationship(back_populates="images")

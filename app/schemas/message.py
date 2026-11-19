"""Request and response schemas for messages."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

MAX_MESSAGE_LENGTH = 4000


class MessageCreate(BaseModel):
    """A message written by the caller."""

    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("content")
    @classmethod
    def _require_visible_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Content cannot be blank")
        return stripped


class MessageResponse(BaseModel):
    """One stored message."""

    id: str
    session_id: str
    sender_id: str
    sender_type: str
    sender_kind: str | None = None
    content: str
    message_type: str = "text"
    created_at: datetime


class MessageList(BaseModel):
    """Cursor paginated message list (newest first)."""

    items: list[MessageResponse]
    has_more: bool

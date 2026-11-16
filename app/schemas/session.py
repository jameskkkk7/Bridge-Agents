"""Request and response schemas for conversations."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    """Open a new conversation."""

    title: str = Field(min_length=1, max_length=200)


class SessionUpdate(BaseModel):
    """Rename a conversation."""

    title: str | None = Field(default=None, min_length=1, max_length=200)


class SessionResponse(BaseModel):
    """One conversation visible to the caller."""

    id: str
    user_id: str
    title: str
    status: str
    human_takeover: bool = False
    unread_count: int = 0
    created_at: datetime
    updated_at: datetime


class SessionList(BaseModel):
    """Paginated conversation list."""

    items: list[SessionResponse]
    total: int
    page: int
    limit: int


class SessionRead(BaseModel):
    """Result of marking a conversation as read."""

    id: str
    unread_count: int = 0
    last_read_at: datetime | None = None

"""Admin conversation and user directory schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AdminSessionItem(BaseModel):
    """One conversation as seen by support staff."""

    id: str
    user_id: str
    user_email: str | None = None
    title: str
    status: str
    human_takeover: bool = False
    created_at: datetime
    updated_at: datetime


class AdminSessionList(BaseModel):
    """Paginated conversation list for support staff."""

    items: list[AdminSessionItem]
    total: int
    page: int
    limit: int


class TakeoverRequest(BaseModel):
    """Turn human takeover on or off."""

    enabled: bool


class SessionStatusRequest(BaseModel):
    """Change a conversation's lifecycle state."""

    status: Literal["active", "closed", "archived"]


class AdminUserItem(BaseModel):
    """One user account in the admin directory."""

    id: str
    email: str | None = None
    role: str
    is_active: bool
    created_at: datetime


class AdminUserList(BaseModel):
    """Paginated user directory."""

    items: list[AdminUserItem]
    total: int
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)

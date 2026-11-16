"""Response schema for uploaded images."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ImageResponse(BaseModel):
    """Metadata of an image attached to a conversation."""

    id: str
    session_id: str
    sender_id: str
    filename: str
    mime_type: str
    file_size: int
    created_at: datetime

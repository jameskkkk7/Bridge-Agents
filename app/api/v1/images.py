"""Image upload and retrieval endpoints."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_session_access, require_user
from app.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.database import get_db
from app.models.message import MessageType, sender_kind
from app.models.user import User
from app.schemas.image import ImageResponse
from app.services.image_service import (
    ALLOWED_IMAGE_TYPES,
    ImageService,
    image_content,
)
from app.services.message_service import MessageService
from app.services.session_service import SessionService

logging.getLogger(__name__)
router = APIRouter()


def _image_response(image) -> ImageResponse:
    return ImageResponse(
        id=image.id,
        session_id=image.session_id,
        sender_id=image.sender_id,
        filename=image.filename,
        mime_type=image.mime_type,
        file_size=image.file_size,
        created_at=image.created_at,
    )


async def _read_limited(file: UploadFile) -> bytes:
    """Read an upload, rejecting oversized bodies before buffering all of it."""
    limit = get_settings().max_image_size
    chunks: list[bytes] = []
    received = 0
    while chunk := await file.read(1024 * 1024):
        received += len(chunk)
        if received > limit:
            raise ValidationError(f"Image too large (max {limit} bytes)")
        chunks.append(chunk)
    return b"".join(chunks)


async def _require_session(db: AsyncSession, session_id: str, user: User):
    session = await SessionService(db).get(session_id)
    if session is None:
        raise NotFoundError("Session not found")
    ensure_session_access(user, session.user_id)
    return session


@router.post(
    "/{session_id}/images",
    response_model=ImageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_image(
    session_id: str,
    file: UploadFile = File(...),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> ImageResponse:
    """Attach an image to a conversation and broadcast it to subscribers."""
    await _require_session(db, session_id, user)

    mime_type = file.content_type or ""
    if mime_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError(f"Unsupported image type: {mime_type or 'unknown'}")

    data = await _read_limited(file)
    image = await ImageService(db).save(
        data=data,
        filename=file.filename or "image",
        mime_type=mime_type,
        session_id=session_id,
        sender_id=user.id,
    )
    message = await MessageService(db).create(
        session_id=session_id,
        sender_id=user.id,
        sender_type=user_sender_type(user),
        content=image_content(image.id),
        message_type=MessageType.IMAGE,
    )

    from app.ws.gateway import connection_manager

    await connection_manager.broadcast_to_session(
        session_id,
        {
            "type": "image",
            "id": message.id,
            "image_id": image.id,
            "session_id": session_id,
            "sender_id": user.id,
            "sender_type": message.sender_type.value,
            "sender_kind": sender_kind(message),
            "filename": image.filename,
            "mime_type": image.mime_type,
            "file_size": image.file_size,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        },
    )
    return _image_response(image)


@router.get("/{session_id}/images/{image_id}")
async def read_image(
    session_id: str,
    image_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Serve one image that belongs to the conversation."""
    await _require_session(db, session_id, user)
    image = await ImageService(db).get(image_id)
    if image is None or image.session_id != session_id:
        raise NotFoundError("Image not found")
    path = ImageService.absolute_path(image)
    if not Path(path).is_file():
        raise NotFoundError("Image not found")
    return FileResponse(path=path, media_type=image.mime_type, filename=image.filename)


def user_sender_type(user: User):
    """Images uploaded through the customer API are customer messages."""
    from app.models.message import SenderType
    from app.models.user import Role

    if user.role in {Role.AGENT, Role.ADMIN}:
        return SenderType.AGENT
    return SenderType.USER

"""Admin conversation endpoints: monitoring, status and human takeover."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_agent
from app.core.exceptions import NotFoundError
from app.models.database import get_db
from app.models.message import sender_kind
from app.models.session import SessionStatus
from app.models.user import User
from app.schemas.admin import (
    AdminSessionItem,
    AdminSessionList,
    SessionStatusRequest,
    TakeoverRequest,
)
from app.schemas.message import MessageList, MessageResponse
from app.services.message_service import MessageService
from app.services.session_service import SessionService
from app.services.takeover_service import apply_takeover

router = APIRouter()


def _session_item(session) -> AdminSessionItem:
    user = getattr(session, "user", None)
    return AdminSessionItem(
        id=session.id,
        user_id=session.user_id,
        user_email=user.email if user else None,
        customer_name=(user.display_name or user.email) if user else None,
        title=session.title,
        status=session.status.value,
        human_takeover=session.human_takeover,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


async def _load(db: AsyncSession, session_id: str):
    session = await SessionService(db).get_with_user(session_id)
    if session is None:
        raise NotFoundError("Session not found")
    return session


@router.get("", response_model=AdminSessionList)
async def list_conversations(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    _: User = Depends(require_agent),
    db: AsyncSession = Depends(get_db),
) -> AdminSessionList:
    """List every conversation, newest first."""
    sessions, total = await SessionService(db).list_all(
        page=page, limit=limit, status=status_filter
    )
    return AdminSessionList(
        items=[_session_item(session) for session in sessions],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{session_id}", response_model=AdminSessionItem)
async def get_conversation(
    session_id: str,
    _: User = Depends(require_agent),
    db: AsyncSession = Depends(get_db),
) -> AdminSessionItem:
    """Return one conversation with its owner."""
    return _session_item(await _load(db, session_id))


@router.get("/{session_id}/messages", response_model=MessageList)
async def list_conversation_messages(
    session_id: str,
    before_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    _: User = Depends(require_agent),
    db: AsyncSession = Depends(get_db),
) -> MessageList:
    """Return one conversation's message history for support staff."""
    await _load(db, session_id)
    messages, has_more = await MessageService(db).list_for_session(
        session_id, before_id=before_id, limit=limit
    )
    return MessageList(
        items=[
            MessageResponse(
                id=message.id,
                session_id=message.session_id,
                sender_id=message.sender_id,
                sender_type=message.sender_type.value,
                sender_kind=sender_kind(message),
                content=message.content,
                message_type=message.message_type.value if message.message_type else "text",
                created_at=message.created_at,
            )
            for message in messages
        ],
        has_more=has_more,
    )


@router.put("/{session_id}/status", response_model=AdminSessionItem)
async def update_conversation_status(
    session_id: str,
    payload: SessionStatusRequest,
    _: User = Depends(require_agent),
    db: AsyncSession = Depends(get_db),
) -> AdminSessionItem:
    """Change the lifecycle state of a conversation."""
    session = await _load(db, session_id)
    session = await SessionService(db).set_status(session, SessionStatus(payload.status))
    return _session_item(session)


@router.put("/{session_id}/takeover", response_model=AdminSessionItem)
async def set_takeover(
    session_id: str,
    payload: TakeoverRequest,
    staff: User = Depends(require_agent),
    db: AsyncSession = Depends(get_db),
) -> AdminSessionItem:
    """Turn human takeover on or off.

    Enabling takeover cancels any in-flight AI reply, flips the flag so future
    customer messages are not answered automatically, and announces the change
    through a system message. Releasing the flag hands the conversation back to
    the assistant.
    """
    session = await apply_takeover(db, session_id, enabled=payload.enabled, actor_id=staff.id)
    if session is None:
        raise NotFoundError("Session not found")
    session = await _load(db, session_id)
    return _session_item(session)

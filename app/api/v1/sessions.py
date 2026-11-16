"""Conversation endpoints for customers and support staff."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_session_access, require_user
from app.core.exceptions import NotFoundError
from app.models.database import get_db
from app.models.session import Session as ChatSession
from app.models.user import User
from app.schemas.session import (
    SessionCreate,
    SessionList,
    SessionRead,
    SessionResponse,
    SessionUpdate,
)
from app.services.session_service import SessionService

router = APIRouter()


def _session_response(session: ChatSession, unread_count: int = 0) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        title=session.title,
        status=session.status.value,
        human_takeover=session.human_takeover,
        unread_count=unread_count,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


async def _load_owned_session(db: AsyncSession, session_id: str, user: User) -> ChatSession:
    session = await SessionService(db).get(session_id)
    if session is None:
        raise NotFoundError("Session not found")
    ensure_session_access(user, session.user_id)
    return session


@router.get("", response_model=SessionList)
async def list_sessions(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> SessionList:
    """List the caller's conversations, newest first, with unread counts."""
    service = SessionService(db)
    sessions, total = await service.list_for_user(
        user.id, page=page, limit=limit, status=status_filter
    )
    unread = await service.unread_counts(user.id)
    return SessionList(
        items=[_session_response(item, unread.get(item.id, 0)) for item in sessions],
        total=total,
        page=page,
        limit=limit,
    )


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreate,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Open a new conversation owned by the caller."""
    session = await SessionService(db).create(user.id, payload.title)
    return _session_response(session)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Return one conversation the caller may access."""
    session = await _load_owned_session(db, session_id, user)
    unread = await SessionService(db).unread_count(session)
    return _session_response(session, unread)


@router.put("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    payload: SessionUpdate,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Rename a conversation."""
    session = await _load_owned_session(db, session_id, user)
    session = await SessionService(db).rename(session, payload.title)
    unread = await SessionService(db).unread_count(session)
    return _session_response(session, unread)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def close_session(
    session_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Close a conversation (it stays readable)."""
    session = await _load_owned_session(db, session_id, user)
    await SessionService(db).close(session)


@router.post("/{session_id}/read", response_model=SessionRead)
async def mark_session_read(
    session_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> SessionRead:
    """Mark the conversation as read for the current user."""
    session = await _load_owned_session(db, session_id, user)
    session = await SessionService(db).mark_read(session)
    return SessionRead(
        id=session.id,
        unread_count=0,
        last_read_at=session.last_read_at,
    )

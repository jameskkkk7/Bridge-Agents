"""Message endpoints: history and customer or staff messages."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_session_access, require_user
from app.core.agent.safety import PromptSafetyError, validate_prompt
from app.core.exceptions import NotFoundError, ValidationError
from app.models.database import get_db
from app.models.message import SenderType, sender_kind
from app.models.user import Role, User
from app.schemas.message import MessageCreate, MessageList, MessageResponse
from app.services.message_service import MessageService
from app.services.session_service import SessionService

STAFF_ROLES = frozenset({Role.AGENT, Role.ADMIN})

router = APIRouter()


def _message_response(message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        session_id=message.session_id,
        sender_id=message.sender_id,
        sender_type=message.sender_type.value,
        sender_kind=sender_kind(message),
        content=message.content,
        message_type=message.message_type.value if message.message_type else "text",
        created_at=message.created_at,
    )


async def _require_session(db: AsyncSession, session_id: str, user: User):
    session = await SessionService(db).get(session_id)
    if session is None:
        raise NotFoundError("Session not found")
    ensure_session_access(user, session.user_id)
    return session


@router.get("/{session_id}/messages", response_model=MessageList)
async def list_messages(
    session_id: str,
    before_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> MessageList:
    """Return the newest messages first, with a cursor for older history."""
    await _require_session(db, session_id, user)
    messages, has_more = await MessageService(db).list_for_session(
        session_id, before_id=before_id, limit=limit
    )
    return MessageList(
        items=[_message_response(message) for message in messages],
        has_more=has_more,
    )


@router.post(
    "/{session_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    session_id: str,
    payload: MessageCreate,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Store a message and trigger an AI reply for customer messages.

    Staff messages never trigger the AI: that is what makes human takeover
    safe while the takeover flag is on.
    """
    await _require_session(db, session_id, user)
    try:
        validate_prompt(payload.content)
    except PromptSafetyError as exc:
        raise ValidationError(str(exc)) from exc

    sender_type = SenderType.AGENT if user.role in STAFF_ROLES else SenderType.USER
    message = await MessageService(db).create(
        session_id=session_id,
        sender_id=user.id,
        sender_type=sender_type,
        content=payload.content,
    )

    from app.services.reply_handler import message_event
    from app.ws.gateway import connection_manager

    await connection_manager.broadcast_to_session(session_id, message_event(message))

    if sender_type is SenderType.USER:
        from app.services.reply_engine import start_reply

        start_reply(request.app, session_id, message.content)

    return _message_response(message)

"""Shared human takeover transition used by the admin API and chat channels."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import MessageType, SenderType
from app.models.session import Session
from app.services.message_service import MessageService
from app.services.reply_engine import cancel_reply
from app.services.reply_handler import message_event
from app.services.session_service import SessionService

TAKEOVER_MESSAGE = "A teammate has taken over this conversation."
RELEASE_MESSAGE = "The conversation is back with the assistant."


async def apply_takeover(
    db: AsyncSession, session_id: str, *, enabled: bool, actor_id: str
) -> Session | None:
    """Flip takeover, cancel in-flight AI work and announce the change.

    Enabling takeover cancels any pending AI reply so a late answer cannot
    arrive after a human started answering. Disabling it hands the session back
    to the assistant. The system message is persisted and broadcast so every
    client and channel sees the same state transition.
    """
    session = await SessionService(db).get(session_id)
    if session is None:
        return None

    if enabled:
        cancel_reply(session_id)

    session = await SessionService(db).set_human_takeover(session, enabled)
    message = await MessageService(db).create(
        session_id=session.id,
        sender_id=actor_id,
        sender_type=SenderType.AGENT,
        content=TAKEOVER_MESSAGE if enabled else RELEASE_MESSAGE,
        message_type=MessageType.SYSTEM,
    )

    from app.ws.gateway import connection_manager

    await connection_manager.broadcast_to_session(session.id, message_event(message))
    return session

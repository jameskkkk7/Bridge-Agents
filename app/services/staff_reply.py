"""Persist and broadcast a human support reply.

Used by the Lark bridge: a whitelisted agent types a plain-text message in the
bound chat and it becomes a real agent message in the conversation, so the
customer's browser receives it over the websocket exactly like a web reply.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import MessageType, SenderType
from app.services.message_service import MessageService
from app.services.reply_handler import message_event
from app.services.session_service import SessionService

LOGGER = logging.getLogger(__name__)


async def send_staff_message(
    db: AsyncSession,
    *,
    session_id: str,
    actor_id: str,
    content: str,
) -> dict | None:
    """Create a human-agent message in a conversation and broadcast it.

    Returns the websocket payload, or ``None`` when the conversation is gone.
    """
    session = await SessionService(db).get(session_id)
    if session is None:
        LOGGER.warning("staff reply dropped: session %s no longer exists", session_id)
        return None

    message = await MessageService(db).create(
        session_id=session_id,
        sender_id=actor_id,
        content=content,
        sender_type=SenderType.AGENT,
        message_type=MessageType.TEXT,
    )
    payload = message_event(message)

    from app.ws.gateway import connection_manager

    await connection_manager.broadcast_to_session(session_id, payload)
    LOGGER.info("staff reply stored in session %s", session_id)
    return payload

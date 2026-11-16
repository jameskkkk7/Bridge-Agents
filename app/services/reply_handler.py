"""Single entry point for persisting and broadcasting agent replies."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message, MessageType, SenderType
from app.services.message_service import MessageService
from app.services.session_service import SessionService

LOGGER = logging.getLogger(__name__)

# Stable sender id for AI generated messages (the assistant is not a user row).
AGENT_SENDER_ID = "00000000-0000-0000-0000-000000000001"


def message_event(message: Message) -> dict:
    """Payload broadcast for a stored message."""
    return {
        "type": "message",
        "id": message.id,
        "session_id": message.session_id,
        "sender_id": message.sender_id,
        "sender_type": message.sender_type.value,
        "content": message.content,
        "message_type": message.message_type.value if message.message_type else "text",
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


async def deliver_agent_reply(
    *,
    db: AsyncSession,
    session_id: str,
    content: str,
    agent_id: str = AGENT_SENDER_ID,
    channel_sender: Callable[[dict], Awaitable[None]] | None = None,
) -> dict | None:
    """Persist an agent reply, broadcast it and optionally notify a channel.

    This is the single write path for AI or human-agent replies so that
    persistence, real-time delivery and channel mirroring stay in sync.
    """
    session = await SessionService(db).get(session_id)
    if session is None:
        LOGGER.warning("agent reply dropped: session %s no longer exists", session_id)
        return None

    message = await MessageService(db).create(
        session_id=session_id,
        sender_id=agent_id,
        sender_type=SenderType.AGENT,
        content=content,
        message_type=MessageType.TEXT,
    )
    payload = message_event(message)

    from app.ws.gateway import connection_manager

    await connection_manager.broadcast_to_session(session_id, payload)

    if channel_sender is not None:
        try:
            await channel_sender(payload)
        except Exception:
            LOGGER.exception("channel delivery failed for session %s", session_id)
    return payload

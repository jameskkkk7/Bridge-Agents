"""Message persistence and cursor pagination."""

from __future__ import annotations

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message, MessageType, SenderType


class MessageService:
    """Persistence helpers for messages."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        session_id: str,
        sender_id: str,
        content: str,
        sender_type: SenderType,
        message_type: MessageType = MessageType.TEXT,
    ) -> Message:
        message = Message(
            content=content,
            sender_type=sender_type,
            sender_id=sender_id,
            session_id=session_id,
            message_type=message_type,
        )
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get(self, message_id: str) -> Message | None:
        result = await self.db.execute(select(Message).where(Message.id == message_id))
        return result.scalar_one_or_none()

    async def list_for_session(
        self, session_id: str, before_id: str | None = None, limit: int = 50
    ) -> tuple[list[Message], bool]:
        """Return the newest messages first, optionally before a cursor.

        The cursor is the ``before_id`` message; older rows are selected by
        ``(created_at, id)`` because ids carry no time ordering by themselves.
        """
        limit = min(max(1, limit), 100)
        query = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(desc(Message.created_at), desc(Message.id))
        )
        if before_id:
            anchor = await self.db.execute(
                select(Message.created_at).where(Message.id == before_id)
            )
            anchor_created_at = anchor.scalar_one_or_none()
            if anchor_created_at is not None:
                query = query.where(
                    or_(
                        Message.created_at < anchor_created_at,
                        and_(
                            Message.created_at == anchor_created_at,
                            Message.id < before_id,
                        ),
                    )
                )
        query = query.limit(limit + 1)
        result = await self.db.execute(query)
        messages = list(result.scalars().all())
        has_more = len(messages) > limit
        return messages[:limit], has_more

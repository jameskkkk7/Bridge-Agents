"""Conversation queries: listing, ownership, unread counts and takeover."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.base import utc_timestamp
from app.models.message import Message, SenderType
from app.models.session import Session, SessionStatus

MAX_PAGE_SIZE = 100


def clamp_page(page: int, limit: int) -> tuple[int, int]:
    """Normalise pagination arguments."""
    return max(1, page), min(max(1, limit), MAX_PAGE_SIZE)


class SessionService:
    """Persistence helpers for conversations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, user_id: str, title: str) -> Session:
        session = Session(user_id=user_id, title=title, status=SessionStatus.ACTIVE)
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get(self, session_id: str) -> Session | None:
        result = await self.db.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()

    async def get_with_user(self, session_id: str) -> Session | None:
        result = await self.db.execute(
            select(Session).options(selectinload(Session.user)).where(Session.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: str, page: int = 1, limit: int = 20, status: str | None = None
    ) -> tuple[list[Session], int]:
        page, limit = clamp_page(page, limit)
        query = select(Session).where(Session.user_id == user_id)
        if status:
            query = query.where(Session.status == SessionStatus(status))
        total = await self._count(query)
        query = query.offset((page - 1) * limit).limit(limit).order_by(Session.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def list_all(
        self, page: int = 1, limit: int = 20, status: str | None = None
    ) -> tuple[list[Session], int]:
        page, limit = clamp_page(page, limit)
        query = select(Session)
        if status:
            query = query.where(Session.status == SessionStatus(status))
        total = await self._count(query)
        query = (
            query.options(selectinload(Session.user))
            .offset((page - 1) * limit)
            .limit(limit)
            .order_by(Session.created_at.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def _count(self, query) -> int:
        count_query = select(func.count()).select_from(query.subquery())
        result = await self.db.execute(count_query)
        return int(result.scalar() or 0)

    async def rename(self, session: Session, title: str | None) -> Session:
        if title:
            session.title = title
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def close(self, session: Session) -> None:
        session.status = SessionStatus.CLOSED
        await self.db.commit()

    async def set_status(self, session: Session, status: SessionStatus) -> Session:
        session.status = status
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def set_human_takeover(self, session: Session, enabled: bool) -> Session:
        """Turn human takeover on or off for one conversation."""
        session.human_takeover = enabled
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def unread_counts(self, user_id: str) -> dict[str, int]:
        """Unread agent messages per conversation for one customer.

        A message is unread when an agent wrote it after the conversation's
        ``last_read_at`` (a null value means never read).
        """
        sessions_result = await self.db.execute(
            select(Session.id, Session.last_read_at).where(Session.user_id == user_id)
        )
        read_at = {str(row[0]): row[1] for row in sessions_result.all()}
        if not read_at:
            return {}
        message_result = await self.db.execute(
            select(Message.session_id, Message.created_at).where(
                Message.session_id.in_(list(read_at)),
                Message.sender_type == SenderType.AGENT,
            )
        )
        counts: dict[str, int] = {}
        for session_id, created_at in message_result.all():
            last_read = read_at[str(session_id)]
            if last_read is None or created_at > last_read:
                key = str(session_id)
                counts[key] = counts.get(key, 0) + 1
        return counts

    async def unread_count(self, session: Session) -> int:
        conditions = [
            Message.session_id == session.id,
            Message.sender_type == SenderType.AGENT,
        ]
        if session.last_read_at is not None:
            conditions.append(Message.created_at > session.last_read_at)
        statement = select(func.count()).select_from(Message).where(*conditions)
        result = await self.db.execute(statement)
        return int(result.scalar() or 0)

    async def mark_read(self, session: Session) -> Session:
        session.last_read_at = utc_timestamp()
        await self.db.commit()
        await self.db.refresh(session)
        return session

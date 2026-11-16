"""ORM model behaviour against SQLite."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import SessionChannel
from app.models.message import Message, MessageType, SenderType
from app.models.session import Session, SessionStatus
from app.models.setting import Setting
from app.models.user import Role, User


async def _create_user(db: AsyncSession, email: str, role: Role = Role.USER) -> User:
    user = User(email=email, role=role)
    db.add(user)
    await db.flush()
    return user


async def test_user_session_and_message_roundtrip(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "widget-user@example.test")
    session = Session(user_id=user.id, title="Refund question")
    db_session.add(session)
    await db_session.flush()
    db_session.add(
        Message(
            session_id=session.id,
            sender_id=user.id,
            sender_type=SenderType.USER,
            content="Can I get a refund?",
        )
    )
    await db_session.commit()

    stored = (
        await db_session.execute(select(Session).where(Session.id == session.id))
    ).scalar_one()
    assert stored.title == "Refund question"
    assert stored.status is SessionStatus.ACTIVE
    assert stored.human_takeover is False
    assert stored.last_read_at is None
    assert stored.user_id == user.id

    message = (await db_session.execute(select(Message))).scalar_one()
    assert message.sender_type is SenderType.USER
    assert message.message_type is MessageType.TEXT


async def test_session_channel_is_unique_per_session_and_channel(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "channel-user@example.test")
    session = Session(user_id=user.id)
    db_session.add(session)
    await db_session.flush()
    db_session.add(SessionChannel(session_id=session.id, channel="lark", external_id="chat-a"))
    await db_session.commit()

    db_session.add(SessionChannel(session_id=session.id, channel="lark", external_id="chat-b"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_setting_can_be_updated_in_place(db_session: AsyncSession) -> None:
    setting = Setting(key="agent_graph_config", value="{}")
    db_session.add(setting)
    await db_session.commit()

    setting.value = '{"nodes": []}'
    await db_session.commit()

    stored = (await db_session.execute(select(Setting))).scalar_one()
    assert stored.key == "agent_graph_config"
    assert stored.value == '{"nodes": []}'

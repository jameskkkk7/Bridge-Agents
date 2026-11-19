"""Human support replies persisted and broadcast like any other agent message."""

from __future__ import annotations

from sqlalchemy import select

from app.models.message import Message, MessageType, SenderType
from app.models.user import Role
from app.services.staff_reply import send_staff_message
from tests.helpers import RecordingBroadcasts, create_session, create_user


async def test_staff_message_is_stored_and_broadcast(db_session, monkeypatch) -> None:
    customer = await create_user(db_session, "staff-reply-customer@example.test")
    session = await create_session(db_session, customer, "Staff reply target")
    staff = await create_user(db_session, "staff-reply-agent@example.test", role=Role.AGENT)

    with RecordingBroadcasts(monkeypatch) as broadcasts:
        payload = await send_staff_message(
            db_session,
            session_id=session.id,
            actor_id=staff.id,
            content="A human is looking into this now.",
        )

    assert payload is not None
    assert payload["sender_type"] == "agent"
    assert payload["content"] == "A human is looking into this now."
    assert broadcasts.of_type("message")[0]["content"] == payload["content"]

    stored = (
        (await db_session.execute(select(Message).where(Message.session_id == session.id)))
        .scalars()
        .all()
    )
    assert len(stored) == 1
    assert stored[0].sender_type is SenderType.AGENT
    assert stored[0].message_type is MessageType.TEXT
    assert stored[0].content == "A human is looking into this now."
    assert stored[0].sender_id == staff.id


async def test_missing_session_returns_none(db_session) -> None:
    payload = await send_staff_message(
        db_session,
        session_id="00000000-0000-0000-0000-000000000000",
        actor_id="11111111-1111-1111-1111-111111111111",
        content="hello",
    )
    assert payload is None

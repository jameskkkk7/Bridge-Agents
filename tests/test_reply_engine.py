"""Background reply engine: persistence, streaming end, takeover, cancellation."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sqlalchemy import select

from app.models.database import SessionLocal
from app.models.message import Message, SenderType
from app.services import reply_engine
from app.services.session_service import SessionService
from tests.helpers import (
    RecordingBroadcasts,
    StubPipeline,
    StuckPipeline,
    add_image,
    create_session,
    create_user,
)


def _app(pipeline) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(agent_pipeline=pipeline, channel_sender=None))


async def _stored_messages(session_id: str) -> list[Message]:
    async with SessionLocal() as db:
        result = await db.execute(select(Message).where(Message.session_id == session_id))
        return list(result.scalars().all())


async def test_reply_is_persisted_and_broadcast_then_stream_closed(db_session, monkeypatch) -> None:
    user = await create_user(db_session, "engine-ok@example.test")
    session = await create_session(db_session, user)
    pipeline = StubPipeline("Here is the answer.")

    with RecordingBroadcasts(monkeypatch) as recorder:
        task = reply_engine.start_reply(_app(pipeline), session.id, "hello")
        await asyncio.wait_for(task, timeout=2.0)

    stored = await _stored_messages(session.id)
    assert [message.sender_type for message in stored] == [SenderType.AGENT]
    assert stored[0].content == "Here is the answer."

    messages = recorder.of_type("message")
    assert messages and messages[0]["content"] == "Here is the answer."
    assert messages[0]["sender_kind"] == "ai"
    assert recorder.of_type("message_chunk")
    assert len(recorder.of_type("stream_end")) == 1


async def test_human_takeover_skips_generation_and_still_closes_the_stream(
    db_session, monkeypatch
) -> None:
    user = await create_user(db_session, "engine-takeover@example.test")
    session = await create_session(db_session, user)
    await SessionService(db_session).set_human_takeover(session, True)
    pipeline = StubPipeline()

    with RecordingBroadcasts(monkeypatch) as recorder:
        task = reply_engine.start_reply(_app(pipeline), session.id, "hello")
        await asyncio.wait_for(task, timeout=2.0)

    assert pipeline.states == []
    assert await _stored_messages(session.id) == []
    assert recorder.of_type("message") == []
    assert recorder.of_type("message_chunk") == []
    assert len(recorder.of_type("stream_end")) == 1


async def test_cancelling_an_in_flight_reply_stops_it_and_closes_the_stream(
    db_session, monkeypatch
) -> None:
    user = await create_user(db_session, "engine-cancel@example.test")
    session = await create_session(db_session, user)
    pipeline = StuckPipeline()

    with RecordingBroadcasts(monkeypatch) as recorder:
        task = reply_engine.start_reply(_app(pipeline), session.id, "hello")
        await asyncio.sleep(0.05)
        assert reply_engine.cancel_reply(session.id) is True
        await asyncio.wait_for(task, timeout=2.0)

    assert await _stored_messages(session.id) == []
    assert recorder.of_type("message") == []
    assert len(recorder.of_type("stream_end")) == 1


async def test_empty_reply_still_closes_the_stream(db_session, monkeypatch) -> None:
    user = await create_user(db_session, "engine-empty@example.test")
    session = await create_session(db_session, user)

    with RecordingBroadcasts(monkeypatch) as recorder:
        task = reply_engine.start_reply(_app(StubPipeline("")), session.id, "hello")
        await asyncio.wait_for(task, timeout=2.0)

    assert await _stored_messages(session.id) == []
    assert len(recorder.of_type("stream_end")) == 1


async def test_history_images_are_attached_to_the_pipeline_state(db_session, monkeypatch) -> None:
    user = await create_user(db_session, "engine-image@example.test")
    session = await create_session(db_session, user)
    await add_image(db_session, session, user.id, data=b"fake-png-bytes")
    pipeline = StubPipeline()

    with RecordingBroadcasts(monkeypatch):
        task = reply_engine.start_reply(_app(pipeline), session.id, "what is this?")
        await asyncio.wait_for(task, timeout=2.0)

    state = pipeline.states[0]["messages"]
    assert state[-1] == {"role": "user", "content": "what is this?"}
    image_entry = next(message for message in state if "images" in message)
    assert image_entry["content"].startswith("[image] ")
    assert image_entry["images"][0].startswith("data:image/png;base64,")


async def test_starting_a_new_reply_cancels_the_previous_one(db_session, monkeypatch) -> None:
    user = await create_user(db_session, "engine-replace@example.test")
    session = await create_session(db_session, user)

    with RecordingBroadcasts(monkeypatch):
        first = reply_engine.start_reply(_app(StuckPipeline()), session.id, "first")
        await asyncio.sleep(0.02)
        second = reply_engine.start_reply(
            _app(StubPipeline("Second answer.")), session.id, "second"
        )
        await asyncio.wait_for(first, timeout=2.0)
        await asyncio.wait_for(second, timeout=2.0)

    stored = await _stored_messages(session.id)
    assert [message.content for message in stored] == ["Second answer."]


def test_cancel_without_a_task_returns_false() -> None:
    assert reply_engine.cancel_reply("no-such-session") is False


async def test_drain_waits_for_running_tasks(db_session, monkeypatch) -> None:
    user = await create_user(db_session, "engine-drain@example.test")
    session = await create_session(db_session, user)
    with RecordingBroadcasts(monkeypatch):
        reply_engine.start_reply(_app(StubPipeline()), session.id, "hello")
        await reply_engine.drain_reply_tasks(timeout=2.0)

    assert await _stored_messages(session.id)

"""WebSocket gateway: auth, subscriptions, streaming end and message limits."""

from __future__ import annotations

import asyncio
import time

from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.models.database import SessionLocal
from app.models.message import Message
from app.models.user import Role
from app.ws.gateway import connection_manager
from tests.helpers import StubPipeline, create_session, create_user, make_token


async def _setup(db_session):
    owner = await create_user(db_session, "ws-owner@example.test")
    session = await create_session(db_session, owner, "Live chat")
    token = make_token(owner.id, "USER")
    other = await create_user(db_session, "ws-other@example.test")
    other_session = await create_session(db_session, other, "Private chat")
    return owner, session, token, other_session


async def test_connection_requires_a_valid_token(app) -> None:
    def scenario() -> int | None:
        client = TestClient(app)
        try:
            with client.websocket_connect("/ws/v1/chat"):
                return None
        except WebSocketDisconnect as exc:
            return exc.code

    assert await asyncio.to_thread(scenario) == 4001

    def invalid_token_scenario() -> int | None:
        client = TestClient(app)
        try:
            with client.websocket_connect("/ws/v1/chat?token=broken"):
                return None
        except WebSocketDisconnect as exc:
            return exc.code

    assert await asyncio.to_thread(invalid_token_scenario) == 4001


async def test_join_own_session_and_receive_the_streamed_reply(app, db_session) -> None:
    _, session, token, _ = await _setup(db_session)
    app.state.agent_pipeline = StubPipeline("Streamed answer.")

    def scenario():
        client = TestClient(app)
        events: list[dict] = []
        with client.websocket_connect(f"/ws/v1/chat?token={token}") as ws:
            events.append(ws.receive_json())
            ws.send_json({"type": "join", "session_id": session.id})
            events.append(ws.receive_json())
            ws.send_json({"type": "message", "session_id": session.id, "content": "hello"})
            deadline = time.time() + 5
            while time.time() < deadline:
                event = ws.receive_json()
                events.append(event)
                if event.get("type") == "stream_end":
                    break
        time.sleep(0.05)
        return events

    events = await asyncio.to_thread(scenario)
    types = [event.get("type") for event in events]
    assert types[0] == "connected"
    assert "joined" in types
    assert "message" in types
    assert types[-1] == "stream_end"
    assert any(
        event.get("type") == "message" and event.get("content") == "Streamed answer."
        for event in events
    )

    async with SessionLocal() as db:
        result = await db.execute(select(Message).where(Message.session_id == session.id))
        stored = list(result.scalars().all())
    assert len(stored) == 2


async def test_cannot_join_or_write_to_another_customers_session(app, db_session) -> None:
    _, _, token, other_session = await _setup(db_session)
    app.state.agent_pipeline = StubPipeline()

    def scenario():
        client = TestClient(app)
        with client.websocket_connect(f"/ws/v1/chat?token={token}") as ws:
            ws.receive_json()
            ws.send_json({"type": "join", "session_id": other_session.id})
            join_error = ws.receive_json()
            ws.send_json({"type": "message", "session_id": other_session.id, "content": "hi"})
            write_error = ws.receive_json()
        return join_error, write_error

    join_error, write_error = await asyncio.to_thread(scenario)
    assert join_error["type"] == "error"
    assert "Access denied" in join_error["message"]
    assert write_error["type"] == "error"


async def test_staff_can_join_any_conversation(app, db_session) -> None:
    _, session, _, _ = await _setup(db_session)
    staff = await create_user(db_session, "ws-staff@example.test", Role.AGENT)
    staff_token = make_token(staff.id, "AGENT")

    def scenario():
        client = TestClient(app)
        with client.websocket_connect(f"/ws/v1/chat?token={staff_token}") as ws:
            ws.receive_json()
            ws.send_json({"type": "join", "session_id": session.id})
            return ws.receive_json()

    joined = await asyncio.to_thread(scenario)
    assert joined == {"type": "joined", "session_id": session.id}


async def test_rate_limited_messages_are_rejected(app, db_session, monkeypatch) -> None:
    _, session, token, _ = await _setup(db_session)
    original = connection_manager.allow_message
    connection_manager.allow_message = lambda user_id: False

    def scenario():
        client = TestClient(app)
        with client.websocket_connect(f"/ws/v1/chat?token={token}") as ws:
            ws.receive_json()
            ws.send_json({"type": "join", "session_id": session.id})
            return ws.receive_json()

    try:
        reply = await asyncio.to_thread(scenario)
    finally:
        connection_manager.allow_message = original
    assert reply["type"] == "error"
    assert "Rate limit" in reply["message"]


async def test_empty_reply_still_ends_the_stream(app, db_session) -> None:
    _, session, token, _ = await _setup(db_session)
    app.state.agent_pipeline = StubPipeline("")

    def scenario():
        client = TestClient(app)
        events: list[dict] = []
        with client.websocket_connect(f"/ws/v1/chat?token={token}") as ws:
            ws.receive_json()
            ws.send_json({"type": "join", "session_id": session.id})
            ws.receive_json()
            ws.send_json({"type": "message", "session_id": session.id, "content": "hello"})
            deadline = time.time() + 5
            while time.time() < deadline:
                event = ws.receive_json()
                events.append(event)
                if event.get("type") == "stream_end":
                    break
        time.sleep(0.05)
        return events

    events = await asyncio.to_thread(scenario)
    types = [event.get("type") for event in events]
    assert types[0] == "message"
    assert types[-1] == "stream_end"
    assert all(event.get("content") != "A safe answer." for event in events)


async def test_ping_is_answered_without_rate_limiting(app, db_session) -> None:
    _, _, token, _ = await _setup(db_session)
    original = connection_manager.allow_message
    connection_manager.allow_message = lambda user_id: False

    def scenario():
        client = TestClient(app)
        with client.websocket_connect(f"/ws/v1/chat?token={token}") as ws:
            ws.receive_json()
            ws.send_json({"type": "ping"})
            return ws.receive_json()

    try:
        reply = await asyncio.to_thread(scenario)
    finally:
        connection_manager.allow_message = original
    assert reply == {"type": "pong"}

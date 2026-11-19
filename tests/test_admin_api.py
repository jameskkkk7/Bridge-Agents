"""Admin APIs: conversation monitoring, status changes and human takeover."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.models.database import SessionLocal
from app.models.message import Message, MessageType, SenderType
from app.models.user import Role
from app.services import reply_engine
from tests.helpers import (
    StuckPipeline,
    add_message,
    bearer,
    create_session,
    create_user,
    make_token,
)


@pytest.fixture
def admin_users(db_session):
    return None


async def _staff(db_session, role: Role, email: str):
    user = await create_user(db_session, email, role)
    return user, bearer(make_token(user.id, role.value))


async def test_admin_conversations_require_staff(db_session) -> None:
    customer = await create_user(db_session, "admin-api-customer@example.test")
    session = await create_session(db_session, customer)
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.get("/api/v1/admin/sessions")).status_code == 401
        customer_response = await client.get(
            "/api/v1/admin/sessions", headers=bearer(make_token(customer.id, "USER"))
        )
        assert customer_response.status_code == 403
        agent, agent_headers = await _staff(db_session, Role.AGENT, "admin-api-agent@example.test")
        listed = await client.get("/api/v1/admin/sessions", headers=agent_headers)
        assert listed.status_code == 200
        body = listed.json()
        assert body["total"] >= 1
        assert any(item["id"] == session.id for item in body["items"])


async def test_admin_can_read_messages_and_change_status(db_session) -> None:
    customer = await create_user(db_session, "admin-api-owner@example.test")
    session = await create_session(db_session, customer, "Status target")
    await add_message(db_session, session, customer.id, SenderType.USER, "hello")
    _, agent_headers = await _staff(db_session, Role.AGENT, "admin-api-agent2@example.test")

    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        detail = await client.get(f"/api/v1/admin/sessions/{session.id}", headers=agent_headers)
        assert detail.status_code == 200
        assert detail.json()["user_email"] == customer.email

        messages = await client.get(
            f"/api/v1/admin/sessions/{session.id}/messages", headers=agent_headers
        )
        assert messages.status_code == 200
        assert messages.json()["items"][0]["content"] == "hello"

        closed = await client.put(
            f"/api/v1/admin/sessions/{session.id}/status",
            json={"status": "closed"},
            headers=agent_headers,
        )
        assert closed.status_code == 200
        assert closed.json()["status"] == "closed"

        missing = await client.get("/api/v1/admin/sessions/not-a-session", headers=agent_headers)
        assert missing.status_code == 404


async def test_takeover_cancels_inflight_reply_and_announces_it(db_session) -> None:
    customer = await create_user(db_session, "admin-api-takeover@example.test")
    session = await create_session(db_session, customer, "Takeover target")
    agent, agent_headers = await _staff(db_session, Role.AGENT, "admin-api-agent3@example.test")

    from app.main import create_app

    app = create_app()
    app.state.agent_pipeline = StuckPipeline()
    task = reply_engine.start_reply(app, session.id, "please answer")
    await asyncio.sleep(0.05)
    assert reply_engine._active_tasks.get(session.id) is task

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.put(
            f"/api/v1/admin/sessions/{session.id}/takeover",
            json={"enabled": True},
            headers=agent_headers,
        )
        assert response.status_code == 200
        assert response.json()["human_takeover"] is True

    await asyncio.wait_for(task, timeout=2.0)
    assert reply_engine._active_tasks.get(session.id) is None

    async with SessionLocal() as db:
        stored = list(
            (await db.execute(select(Message).where(Message.session_id == session.id)))
            .scalars()
            .all()
        )
    system_messages = [m for m in stored if m.message_type is MessageType.SYSTEM]
    assert system_messages
    assert system_messages[0].sender_id == agent.id
    assert "taken over" in system_messages[0].content

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://testserver"
    ) as client:
        released = await client.put(
            f"/api/v1/admin/sessions/{session.id}/takeover",
            json={"enabled": False},
            headers=agent_headers,
        )
        assert released.status_code == 200
        assert released.json()["human_takeover"] is False


async def test_user_directory_is_admin_only(db_session) -> None:
    admin, admin_headers = await _staff(db_session, Role.ADMIN, "admin-api-admin@example.test")
    _, agent_headers = await _staff(db_session, Role.AGENT, "admin-api-agent4@example.test")

    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.get("/api/v1/admin/users", headers=agent_headers)).status_code == 403
        response = await client.get("/api/v1/admin/users", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 2
        assert any(item["id"] == admin.id for item in body["items"])


async def test_admin_conversation_shows_customer_nickname(db_session) -> None:
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app
    from tests.helpers import create_session, create_user

    customer = await create_user(db_session, "admin-api-nickname@example.test")
    customer.display_name = "小明"
    await db_session.commit()
    session = await create_session(db_session, customer)
    _, agent_headers = await _staff(db_session, Role.AGENT, "admin-api-nick3@example.test")

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        listed = await client.get("/api/v1/admin/sessions", headers=agent_headers)
        assert listed.status_code == 200
        item = next(row for row in listed.json()["items"] if row["id"] == session.id)
        assert item["customer_name"] == "小明"

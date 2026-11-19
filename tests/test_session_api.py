"""Conversation endpoints: creation, ownership, unread counts and closing."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import SenderType
from app.services.session_service import SessionService
from tests.helpers import add_message, bearer, create_session, create_user, dev_login


async def _login(client: AsyncClient, role: str = "user") -> tuple[str, str]:
    body = await dev_login(client, role)
    return body["user"]["id"], body["access_token"]


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/sessions")).status_code == 401


async def test_create_list_and_fetch_a_conversation(client: AsyncClient) -> None:
    _, token = await _login(client)
    created = await client.post(
        "/api/v1/sessions", json={"title": "Refund question"}, headers=bearer(token)
    )
    assert created.status_code == 201
    session = created.json()
    assert session["title"] == "Refund question"
    assert session["status"] == "active"
    assert session["human_takeover"] is False

    listed = await client.get("/api/v1/sessions", headers=bearer(token))
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == session["id"]

    fetched = await client.get(f"/api/v1/sessions/{session['id']}", headers=bearer(token))
    assert fetched.status_code == 200
    assert fetched.json()["id"] == session["id"]


async def test_rename_and_close_a_conversation(client: AsyncClient) -> None:
    _, token = await _login(client)
    session = (
        await client.post("/api/v1/sessions", json={"title": "Old"}, headers=bearer(token))
    ).json()

    renamed = await client.put(
        f"/api/v1/sessions/{session['id']}", json={"title": "New"}, headers=bearer(token)
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "New"

    closed = await client.delete(f"/api/v1/sessions/{session['id']}", headers=bearer(token))
    assert closed.status_code == 204
    fetched = await client.get(f"/api/v1/sessions/{session['id']}", headers=bearer(token))
    assert fetched.json()["status"] == "closed"


async def test_customers_cannot_read_another_customers_conversation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await create_user(db_session, "owner@example.test")
    intruder = await create_user(db_session, "intruder@example.test")
    session = await create_session(db_session, owner, "Private")
    token = bearer(_token_for(intruder.id))

    response = await client.get(f"/api/v1/sessions/{session.id}", headers=token)
    assert response.status_code == 403


def _token_for(user_id: str) -> str:
    from tests.helpers import make_token

    return make_token(user_id, "USER")


async def test_unread_counts_and_mark_read(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await create_user(db_session, "unread@example.test")
    session = await create_session(db_session, user)
    await add_message(db_session, session, "agent-1", SenderType.AGENT, "Hello there")
    token = bearer(_token_for(user.id))

    fetched = await client.get(f"/api/v1/sessions/{session.id}", headers=token)
    assert fetched.json()["unread_count"] == 1

    read = await client.post(f"/api/v1/sessions/{session.id}/read", headers=token)
    assert read.status_code == 200
    assert read.json()["unread_count"] == 0
    assert read.json()["last_read_at"] is not None

    after = await client.get(f"/api/v1/sessions/{session.id}", headers=token)
    assert after.json()["unread_count"] == 0


async def test_takeover_flag_is_exposed(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await create_user(db_session, "takeover@example.test")
    session = await create_session(db_session, user)
    await SessionService(db_session).set_human_takeover(session, True)
    token = bearer(_token_for(user.id))

    fetched = await client.get(f"/api/v1/sessions/{session.id}", headers=token)
    assert fetched.json()["human_takeover"] is True


async def test_demo_customers_do_not_see_each_others_conversations(client: AsyncClient) -> None:
    alice = await client.post(
        "/api/v1/auth/dev-login",
        params={"role": "user", "client_id": "browser-alice-1111", "name": "Alice"},
    )
    bob = await client.post(
        "/api/v1/auth/dev-login",
        params={"role": "user", "client_id": "browser-bob-2222", "name": "Bob"},
    )
    alice_headers = bearer(alice.json()["access_token"])
    bob_headers = bearer(bob.json()["access_token"])
    created = await client.post(
        "/api/v1/sessions", json={"title": "Alice refund"}, headers=alice_headers
    )
    assert created.status_code == 201

    alice_list = await client.get("/api/v1/sessions", headers=alice_headers)
    bob_list = await client.get("/api/v1/sessions", headers=bob_headers)
    assert any(item["id"] == created.json()["id"] for item in alice_list.json()["items"])
    assert bob_list.json()["total"] == 0

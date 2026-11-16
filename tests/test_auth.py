"""Authentication endpoints and role gates."""

from __future__ import annotations

import jwt
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import require_admin, require_agent
from app.config import get_settings
from app.main import create_app

SECRET = "test-secret-key-for-pytest-only-32b"
ISSUER = "bridge-agents-test"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _dev_login(client: AsyncClient, role: str = "user") -> dict:
    response = await client.post(f"/api/v1/auth/dev-login?role={role}")
    assert response.status_code == 200, response.text
    return response.json()


async def test_dev_login_creates_a_user_account(client: AsyncClient) -> None:
    body = await _dev_login(client)
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "USER"
    assert body["user"]["email"].startswith("dev-")

    me = await client.get("/api/v1/auth/me", headers=_bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["id"] == body["user"]["id"]


async def test_each_demo_role_has_a_distinct_account(client: AsyncClient) -> None:
    user = await _dev_login(client, "user")
    agent = await _dev_login(client, "agent")
    admin = await _dev_login(client, "admin")
    assert user["user"]["role"] == "USER"
    assert agent["user"]["role"] == "AGENT"
    assert admin["user"]["role"] == "ADMIN"
    assert len({user["user"]["id"], agent["user"]["id"], admin["user"]["id"]}) == 3


async def test_repeated_logins_reuse_the_same_account(client: AsyncClient) -> None:
    first = await _dev_login(client, "agent")
    second = await _dev_login(client, "agent")
    assert first["user"]["id"] == second["user"]["id"]


async def test_me_requires_a_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_me_rejects_a_malformed_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me", headers=_bearer("not-a-jwt"))
    assert response.status_code == 401
    assert response.json()["error"] == "AuthError"


async def test_dev_login_is_not_mounted_when_disabled() -> None:
    settings = get_settings().model_copy(update={"allow_dev_login": False})
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/v1/auth/dev-login")
    assert response.status_code == 404


async def test_dev_login_is_absent_in_production() -> None:
    settings = get_settings().model_copy(update={"allow_dev_login": True, "app_env": "production"})
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/v1/auth/dev-login")
    assert response.status_code == 404


async def test_verify_endpoint_returns_the_identity(client: AsyncClient) -> None:
    token = jwt.encode(
        {"sub": "external-42", "role": "AGENT", "iss": ISSUER}, SECRET, algorithm="HS256"
    )
    response = await client.post("/api/v1/auth/verify", json={"token": token})
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == token
    assert body["user"]["role"] == "AGENT"

    me = await client.get("/api/v1/auth/me", headers=_bearer(token))
    assert me.json()["role"] == "AGENT"
    assert me.json()["id"] == "external-42"


async def test_verify_endpoint_rejects_an_invalid_token(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/verify", json={"token": "broken"})
    assert response.status_code == 401


async def test_stored_role_is_not_rewritten_by_later_tokens(client: AsyncClient) -> None:
    agent_token = jwt.encode(
        {"sub": "external-7", "role": "AGENT", "iss": ISSUER}, SECRET, algorithm="HS256"
    )
    user_token = jwt.encode(
        {"sub": "external-7", "role": "USER", "iss": ISSUER}, SECRET, algorithm="HS256"
    )
    first = await client.get("/api/v1/auth/me", headers=_bearer(agent_token))
    second = await client.get("/api/v1/auth/me", headers=_bearer(user_token))
    assert first.json()["role"] == "AGENT"
    assert second.json()["role"] == "AGENT"


async def test_role_gates_protect_staff_and_admin_endpoints(client: AsyncClient, app) -> None:
    async def agent_probe(user=Depends(require_agent)) -> dict[str, str]:
        return {"role": user.role.value}

    async def admin_probe(user=Depends(require_admin)) -> dict[str, str]:
        return {"role": user.role.value}

    app.add_api_route("/_test/staff", agent_probe)
    app.add_api_route("/_test/admin", admin_probe)

    user = await _dev_login(client, "user")
    agent = await _dev_login(client, "agent")
    admin = await _dev_login(client, "admin")

    assert (await client.get("/_test/staff")).status_code == 401
    assert (
        await client.get("/_test/staff", headers=_bearer(user["access_token"]))
    ).status_code == 403
    assert (
        await client.get("/_test/staff", headers=_bearer(agent["access_token"]))
    ).status_code == 200
    assert (
        await client.get("/_test/admin", headers=_bearer(agent["access_token"]))
    ).status_code == 403
    assert (
        await client.get("/_test/admin", headers=_bearer(admin["access_token"]))
    ).status_code == 200

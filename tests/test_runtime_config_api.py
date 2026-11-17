"""Admin API for the editable agent graph."""

from __future__ import annotations

from httpx import AsyncClient

from app.core.agent.factory import default_graph_config


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _login(client: AsyncClient, role: str) -> str:
    response = await client.post(f"/api/v1/auth/dev-login?role={role}")
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def test_runtime_config_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/admin/runtime-config/agent-graph")
    assert response.status_code == 401


async def test_customers_cannot_read_the_graph(client: AsyncClient) -> None:
    token = await _login(client, "user")
    response = await client.get("/api/v1/admin/runtime-config/agent-graph", headers=_bearer(token))
    assert response.status_code == 403


async def test_agent_reads_the_default_graph(client: AsyncClient) -> None:
    token = await _login(client, "agent")
    response = await client.get(
        "/api/v1/admin/runtime-config/agent-graph-config", headers=_bearer(token)
    )
    assert response.status_code == 200
    body = response.json()
    assert [node["id"] for node in body["nodes"]][:3] == [
        "__start__",
        "system_node",
        "retrieval_node",
    ]
    assert any(node["type"] == "review" for node in body["nodes"])


async def test_agent_renders_mermaid(client: AsyncClient) -> None:
    token = await _login(client, "agent")
    response = await client.get("/api/v1/admin/runtime-config/agent-graph", headers=_bearer(token))
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "mermaid"
    assert "agent_node" in body["diagram"]
    assert "review_node" in body["diagram"]


async def test_agent_tool_list_is_empty_without_enabled_plugins(
    client: AsyncClient,
) -> None:
    token = await _login(client, "agent")
    response = await client.get("/api/v1/admin/runtime-config/agent-tools", headers=_bearer(token))
    assert response.status_code == 200
    assert response.json() == []


async def test_save_requires_a_non_empty_system_prompt(client: AsyncClient) -> None:
    token = await _login(client, "agent")
    config = default_graph_config()
    config["nodes"][1]["config"]["system_prompt"] = ""
    response = await client.put(
        "/api/v1/admin/runtime-config/agent-graph-config",
        json=config,
        headers=_bearer(token),
    )
    assert response.status_code == 422
    assert "system" in response.json()["message"].lower()

    current = await client.get(
        "/api/v1/admin/runtime-config/agent-graph-config", headers=_bearer(token)
    )
    assert current.json()["nodes"][1]["config"]["system_prompt"]


async def test_save_then_reset_restores_the_default_graph(client: AsyncClient) -> None:
    token = await _login(client, "agent")
    config = default_graph_config()
    config["nodes"][1]["config"]["system_prompt"] = "You are a test bot."
    saved = await client.put(
        "/api/v1/admin/runtime-config/agent-graph-config",
        json=config,
        headers=_bearer(token),
    )
    assert saved.status_code == 200
    assert saved.json()["saved"] is True

    current = await client.get(
        "/api/v1/admin/runtime-config/agent-graph-config", headers=_bearer(token)
    )
    assert current.status_code == 200
    assert current.json()["nodes"][1]["config"]["system_prompt"] == "You are a test bot."

    diagram = await client.get("/api/v1/admin/runtime-config/agent-graph", headers=_bearer(token))
    assert "agent_node" in diagram.json()["diagram"]

    reset = await client.delete(
        "/api/v1/admin/runtime-config/agent-graph-config", headers=_bearer(token)
    )
    assert reset.status_code == 200
    assert reset.json()["deleted"] is True

    restored = await client.get(
        "/api/v1/admin/runtime-config/agent-graph-config", headers=_bearer(token)
    )
    assert restored.json()["nodes"][1]["config"]["system_prompt"] != "You are a test bot."

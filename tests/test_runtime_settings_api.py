"""Runtime model configuration and agent prompt endpoints."""

from __future__ import annotations

from bridge_agents.agent.prompts import DEFAULT_SYSTEM_PROMPT
from httpx import AsyncClient
from sqlalchemy import select

from app.models.setting import Setting
from app.services.model_config_service import MODEL_CONFIG_KEY
from tests.helpers import bearer, dev_login


async def _agent_headers(client: AsyncClient) -> dict[str, str]:
    login = await dev_login(client, "agent")
    return bearer(login["access_token"])


async def _settings_row(db_session) -> Setting | None:
    result = await db_session.execute(select(Setting).where(Setting.key == MODEL_CONFIG_KEY))
    return result.scalar_one_or_none()


async def test_model_config_requires_staff(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/admin/runtime-config/model-config")).status_code == 401
    customer = await dev_login(client, "user")
    response = await client.get(
        "/api/v1/admin/runtime-config/model-config", headers=bearer(customer["access_token"])
    )
    assert response.status_code == 403


async def test_model_config_defaults_to_environment(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/admin/runtime-config/model-config", headers=await _agent_headers(client)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "environment"
    assert body["model"] == "mock-model"
    assert body["api_key_source"] == "environment"
    assert body["api_key_configured"] is True
    assert "api_key" not in body


async def test_saving_model_config_hides_the_secret_and_applies_it(
    client: AsyncClient, app, db_session
) -> None:
    response = await client.put(
        "/api/v1/admin/runtime-config/model-config",
        json={
            "base_url": "https://llm.example.test/v1/",
            "model": "custom-model",
            "temperature": 0.2,
            "timeout": 20,
            "max_retries": 1,
            "thinking_enabled": True,
            "api_key": "sk-test-secret-value",
        },
        headers=await _agent_headers(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "runtime"
    assert body["base_url"] == "https://llm.example.test/v1"
    assert body["model"] == "custom-model"
    assert body["temperature"] == 0.2
    assert body["thinking_enabled"] is True
    assert body["api_key_source"] == "runtime"
    assert body["api_key_configured"] is True
    assert "sk-test-secret-value" not in response.text

    row = await _settings_row(db_session)
    assert row is not None
    assert "sk-test-secret-value" not in row.value
    assert "api_key_encrypted" in row.value

    pipeline = app.state.agent_pipeline
    assert pipeline._settings.openai_model == "custom-model"
    assert pipeline._settings.openai_base_url == "https://llm.example.test/v1"
    assert pipeline._settings.openai_api_key == "sk-test-secret-value"

    fetched = await client.get(
        "/api/v1/admin/runtime-config/model-config", headers=await _agent_headers(client)
    )
    assert "sk-test-secret-value" not in fetched.text
    assert fetched.json()["model"] == "custom-model"


async def test_keeping_the_stored_key_when_updating_other_fields(
    client: AsyncClient, db_session
) -> None:
    headers = await _agent_headers(client)
    first = await client.put(
        "/api/v1/admin/runtime-config/model-config",
        json={
            "base_url": "https://llm.example.test/v1",
            "model": "first-model",
            "api_key": "sk-first-key",
        },
        headers=headers,
    )
    assert first.status_code == 200

    second = await client.put(
        "/api/v1/admin/runtime-config/model-config",
        json={"base_url": "https://llm.example.test/v1", "model": "second-model"},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["model"] == "second-model"
    assert second.json()["api_key_source"] == "runtime"

    cleared = await client.put(
        "/api/v1/admin/runtime-config/model-config",
        json={
            "base_url": "https://llm.example.test/v1",
            "model": "second-model",
            "clear_api_key": True,
        },
        headers=headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["api_key_source"] == "environment"


async def test_reset_model_config_restores_environment(client: AsyncClient, app) -> None:
    headers = await _agent_headers(client)
    saved = await client.put(
        "/api/v1/admin/runtime-config/model-config",
        json={"base_url": "https://llm.example.test/v1", "model": "temporary-model"},
        headers=headers,
    )
    assert saved.status_code == 200

    reset = await client.delete("/api/v1/admin/runtime-config/model-config", headers=headers)
    assert reset.status_code == 200
    assert reset.json()["source"] == "environment"
    assert reset.json()["model"] == "mock-model"
    assert app.state.agent_pipeline._settings.openai_model == "mock-model"


async def test_model_config_validation(client: AsyncClient) -> None:
    headers = await _agent_headers(client)
    for payload in (
        {"base_url": "ftp://example.test", "model": "m"},
        {"base_url": "https://example.test/v1", "model": ""},
        {"base_url": "https://example.test/v1", "model": "m", "temperature": 3},
        {"base_url": "https://user:pass@example.test/v1", "model": "m"},
    ):
        response = await client.put(
            "/api/v1/admin/runtime-config/model-config", json=payload, headers=headers
        )
        assert response.status_code == 422, payload


async def test_agent_prompt_round_trip(client: AsyncClient, app, db_session) -> None:
    headers = await _agent_headers(client)
    default = await client.get("/api/v1/admin/runtime-config/agent-prompt", headers=headers)
    assert default.status_code == 200
    assert default.json()["source"] == "default_graph"
    assert default.json()["system_prompt"] == DEFAULT_SYSTEM_PROMPT

    prompt = "You are a concise Chinese support assistant for Widget Cloud."
    saved = await client.put(
        "/api/v1/admin/runtime-config/agent-prompt",
        json={"system_prompt": prompt},
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json() == {"system_prompt": prompt, "source": "saved_graph"}

    fetched = await client.get("/api/v1/admin/runtime-config/agent-prompt", headers=headers)
    assert fetched.json()["system_prompt"] == prompt
    assert fetched.json()["source"] == "saved_graph"

    graph = await client.get("/api/v1/admin/runtime-config/agent-graph-config", headers=headers)
    assert graph.status_code == 200
    system_prompts = [
        node["config"]["system_prompt"]
        for node in graph.json()["nodes"]
        if node["type"] == "system"
    ]
    assert system_prompts and all(value == prompt for value in system_prompts)
    assert app.state.agent_pipeline._role_prompt == prompt

    row = (
        await db_session.execute(select(Setting).where(Setting.key == "agent_graph_config"))
    ).scalar_one_or_none()
    assert row is not None
    assert prompt in row.value


async def test_agent_prompt_requires_staff_and_content(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/admin/runtime-config/agent-prompt")).status_code == 401
    customer = await dev_login(client, "user")
    headers = bearer(customer["access_token"])
    assert (
        await client.get("/api/v1/admin/runtime-config/agent-prompt", headers=headers)
    ).status_code == 403

    agent_headers = await _agent_headers(client)
    empty = await client.put(
        "/api/v1/admin/runtime-config/agent-prompt",
        json={"system_prompt": "   "},
        headers=agent_headers,
    )
    assert empty.status_code == 422


async def test_model_config_defaults_report_openai_provider(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/admin/runtime-config/model-config", headers=await _agent_headers(client)
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "openai"


async def test_saving_azure_provider_builds_an_azure_client(client: AsyncClient, app) -> None:
    from langchain_openai import AzureChatOpenAI

    response = await client.put(
        "/api/v1/admin/runtime-config/model-config",
        json={
            "provider": "azure",
            "base_url": "https://example-resource.openai.azure.com",
            "model": "gpt-4o-mini",
            "api_version": "2024-10-21",
            "api_key": "sk-azure-test",
        },
        headers=await _agent_headers(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "azure"
    assert body["api_version"] == "2024-10-21"
    assert body["base_url"] == "https://example-resource.openai.azure.com"

    pipeline = app.state.agent_pipeline
    assert isinstance(pipeline._chat_model, AzureChatOpenAI)
    assert pipeline._settings.llm_provider == "azure"
    assert pipeline._settings.openai_api_version == "2024-10-21"


async def test_unknown_provider_is_rejected(client: AsyncClient) -> None:
    response = await client.put(
        "/api/v1/admin/runtime-config/model-config",
        json={
            "provider": "not-a-vendor",
            "base_url": "https://llm.example.test/v1",
            "model": "some-model",
        },
        headers=await _agent_headers(client),
    )
    assert response.status_code == 422


async def test_default_agent_prompt_is_saveable(client: AsyncClient) -> None:
    response = await client.put(
        "/api/v1/admin/runtime-config/agent-prompt",
        json={"system_prompt": DEFAULT_SYSTEM_PROMPT},
        headers=await _agent_headers(client),
    )
    assert response.status_code == 200, response.text
    assert response.json()["system_prompt"] == DEFAULT_SYSTEM_PROMPT


async def test_model_catalog_requires_staff(client: AsyncClient) -> None:
    assert (
        await client.post(
            "/api/v1/admin/runtime-config/model-config/models",
            json={"provider": "openai", "base_url": "https://llm.example.test/v1"},
        )
    ).status_code == 401
    customer = await dev_login(client, "user")
    response = await client.post(
        "/api/v1/admin/runtime-config/model-config/models",
        json={"provider": "openai", "base_url": "https://llm.example.test/v1"},
        headers=bearer(customer["access_token"]),
    )
    assert response.status_code == 403


async def test_model_catalog_returns_discovered_models(client: AsyncClient, monkeypatch) -> None:
    headers = await _agent_headers(client)
    captured: dict = {}

    async def fake_discover(**kwargs) -> list[str]:
        captured.update(kwargs)
        return ["model-b", "model-a"]

    monkeypatch.setattr("app.api.v1.admin.runtime_config.discover_models", fake_discover)
    response = await client.post(
        "/api/v1/admin/runtime-config/model-config/models",
        json={
            "provider": "openai",
            "base_url": "https://llm.example.test/v1",
            "api_version": "2024-10-21",
            "api_key": "sk-request-key",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["models"] == ["model-b", "model-a"]
    assert body["api_key_source"] == "request"
    assert captured["api_key"] == "sk-request-key"
    assert "sk-request-key" not in response.text


async def test_model_catalog_falls_back_to_the_stored_key(client: AsyncClient, monkeypatch) -> None:
    headers = await _agent_headers(client)
    saved = await client.put(
        "/api/v1/admin/runtime-config/model-config",
        json={
            "base_url": "https://llm.example.test/v1",
            "model": "stored-model",
            "api_key": "sk-stored-key",
        },
        headers=headers,
    )
    assert saved.status_code == 200
    captured: dict = {}

    async def fake_discover(**kwargs) -> list[str]:
        captured.update(kwargs)
        return ["stored-model"]

    monkeypatch.setattr("app.api.v1.admin.runtime_config.discover_models", fake_discover)
    response = await client.post(
        "/api/v1/admin/runtime-config/model-config/models",
        json={"provider": "openai", "base_url": "https://llm.example.test/v1"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["api_key_source"] == "runtime"
    assert captured["api_key"] == "sk-stored-key"

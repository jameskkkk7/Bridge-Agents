"""Model profile validation probes."""

from __future__ import annotations

import httpx

from app.services.model_validation_service import validate_model_config


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def test_model_list_match_is_enough() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        return httpx.Response(200, json={"data": [{"id": "model-a"}]})

    valid, message = await validate_model_config(
        provider="openai",
        base_url="https://llm.example.test/v1",
        api_version="",
        api_key="sk-secret",
        model="model-a",
        transport=_transport(handler),
    )

    assert valid is True
    assert "model-a" in message
    assert calls == ["GET /v1/models"]


async def test_chat_ping_fallback_when_listing_is_unavailable() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404, json={"error": "not found"})
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "p"}}]})

    valid, _ = await validate_model_config(
        provider="openai",
        base_url="https://llm.example.test/v1",
        api_version="",
        api_key="sk-secret",
        model="model-a",
        transport=_transport(handler),
    )

    assert valid is True
    assert seen["url"] == "https://llm.example.test/v1/chat/completions"
    assert seen["authorization"] == "Bearer sk-secret"


async def test_rejected_key_is_reported_without_leaking_it() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404)
        return httpx.Response(401, json={"error": "bad key"})

    valid, message = await validate_model_config(
        provider="openai",
        base_url="https://llm.example.test/v1",
        api_version="",
        api_key="sk-must-not-leak",
        model="model-a",
        transport=_transport(handler),
    )

    assert valid is False
    assert "401" in message
    assert "sk-must-not-leak" not in message


async def test_missing_model_or_key_is_rejected() -> None:
    valid, message = await validate_model_config(
        provider="openai",
        base_url="https://llm.example.test/v1",
        api_version="",
        api_key="sk-secret",
        model="",
    )
    assert valid is False
    assert "model" in message.lower()

    valid, message = await validate_model_config(
        provider="openai",
        base_url="https://llm.example.test/v1",
        api_version="",
        api_key="",
        model="model-a",
    )
    assert valid is False
    assert "api key" in message.lower()


async def test_azure_uses_deployment_chat_path() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404)
        seen["url"] = str(request.url)
        seen["api_key"] = request.headers.get("api-key")
        return httpx.Response(200, json={"choices": []})

    valid, _ = await validate_model_config(
        provider="azure",
        base_url="https://resource.openai.azure.com",
        api_version="2024-10-21",
        api_key="azure-key",
        model="deployment-a",
        transport=_transport(handler),
    )

    assert valid is True
    assert seen["url"] is not None
    assert "/openai/deployments/deployment-a/chat/completions" in seen["url"]
    assert "api-version=2024-10-21" in seen["url"]
    assert seen["api_key"] == "azure-key"

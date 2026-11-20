"""Provider model discovery used by the Studio model picker."""

from __future__ import annotations

import httpx
import pytest

from app.core.exceptions import ExternalServiceError
from app.services.model_catalog_service import discover_models


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def test_openai_compatible_models_are_sorted_and_deduplicated() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [{"id": "model-b"}, {"id": "model-a"}, {"id": "model-a"}],
            },
        )

    models = await discover_models(
        provider="deepseek",
        base_url="https://llm.example.test/v1/",
        api_version="",
        api_key="sk-secret",
        transport=_transport(handler),
    )

    assert models == ["model-a", "model-b"]
    assert seen["url"] == "https://llm.example.test/v1/models"
    assert seen["authorization"] == "Bearer sk-secret"


async def test_azure_lists_deployments_with_the_api_key_header() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["api_key"] = request.headers.get("api-key")
        return httpx.Response(200, json={"data": [{"id": "deployment-a"}]})

    models = await discover_models(
        provider="azure",
        base_url="https://resource.openai.azure.com",
        api_version="2024-10-21",
        api_key="azure-key",
        transport=_transport(handler),
    )

    assert models == ["deployment-a"]
    assert seen["url"] is not None
    assert seen["url"].startswith(
        "https://resource.openai.azure.com/openai/deployments?api-version=2024-10-21"
    )
    assert seen["api_key"] == "azure-key"


async def test_authentication_failure_is_reported_without_leaking_the_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    with pytest.raises(ExternalServiceError) as caught:
        await discover_models(
            provider="openai",
            base_url="https://llm.example.test/v1",
            api_version="",
            api_key="sk-must-not-leak",
            transport=_transport(handler),
        )

    assert "401" in caught.value.message
    assert "sk-must-not-leak" not in caught.value.message


async def test_empty_model_list_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    with pytest.raises(ExternalServiceError):
        await discover_models(
            provider="openai",
            base_url="https://llm.example.test/v1",
            api_version="",
            api_key="sk-secret",
            transport=_transport(handler),
        )


async def test_timeout_is_reported_as_an_external_service_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("too slow", request=request)

    with pytest.raises(ExternalServiceError):
        await discover_models(
            provider="openai",
            base_url="https://llm.example.test/v1",
            api_version="",
            api_key="sk-secret",
            transport=_transport(handler),
        )

"""Discover the models an LLM endpoint exposes.

The Studio no longer asks operators to type a model name: once an API key is
available the server asks the provider for its model list and the UI offers a
dropdown. OpenAI-compatible endpoints expose ``GET /models``; Azure OpenAI lists
deployments through ``GET /openai/deployments`` with the configured API version.
"""

from __future__ import annotations

import logging

import httpx

from app.core.exceptions import ExternalServiceError

LOGGER = logging.getLogger(__name__)

MODEL_LIST_TIMEOUT_SECONDS = 10.0
MAX_MODELS = 500
AZURE_PROVIDERS = frozenset({"azure", "azure-openai", "azure_openai"})


def _models_from_payload(payload: object) -> list[str]:
    """Extract model ids from the common OpenAI/Azure list shapes."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        models = payload.get("models") if isinstance(payload, dict) else None
        data = models if isinstance(models, list) else []
    names: list[str] = []
    for item in data:
        name: object = item
        if isinstance(item, dict):
            name = item.get("id") or item.get("name") or item.get("model")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return sorted(dict.fromkeys(names))[:MAX_MODELS]


async def discover_models(
    *,
    provider: str,
    base_url: str,
    api_version: str,
    api_key: str | None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[str]:
    """Return the model ids exposed by the configured endpoint.

    ``transport`` exists for tests; production calls use a short timeout and do
    not follow redirects. Errors never include the API key or response body.
    """
    provider_name = (provider or "openai").strip().lower()
    endpoint = base_url.strip().rstrip("/")
    headers = {"Accept": "application/json"}
    if api_key:
        if provider_name in AZURE_PROVIDERS:
            headers["api-key"] = api_key
        else:
            headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(
            timeout=MODEL_LIST_TIMEOUT_SECONDS,
            transport=transport,
            follow_redirects=False,
        ) as client:
            if provider_name in AZURE_PROVIDERS:
                version = api_version.strip() or "2024-10-21"
                response = await client.get(
                    f"{endpoint}/openai/deployments",
                    params={"api-version": version},
                    headers=headers,
                )
                if response.status_code == 404:
                    response = await client.get(
                        f"{endpoint}/openai/models",
                        params={"api-version": version},
                        headers=headers,
                    )
            else:
                response = await client.get(f"{endpoint}/models", headers=headers)
    except httpx.TimeoutException as exc:
        raise ExternalServiceError("The model endpoint did not respond in time") from exc
    except httpx.HTTPError as exc:
        raise ExternalServiceError("Could not reach the model endpoint") from exc

    if response.status_code in (401, 403):
        raise ExternalServiceError(
            f"The model endpoint rejected the API key (HTTP {response.status_code})"
        )
    if response.status_code >= 400:
        raise ExternalServiceError(f"The model endpoint returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ExternalServiceError("The model endpoint returned invalid JSON") from exc

    models = _models_from_payload(payload)
    if not models:
        raise ExternalServiceError("The model endpoint returned no models")
    LOGGER.info("discovered %d model(s) from %s", len(models), endpoint)
    return models

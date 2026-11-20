"""Validate a saved model API profile.

Validation is intentionally cheap and explicit: first ask the provider for its
model list and check the configured model is present; when the provider has no
compatible list endpoint, send one minimal chat completion. The API key is never
logged or returned.
"""

from __future__ import annotations

import logging

import httpx

from app.core.exceptions import ExternalServiceError
from app.services.model_catalog_service import AZURE_PROVIDERS, discover_models

LOGGER = logging.getLogger(__name__)

VALIDATION_TIMEOUT_SECONDS = 15.0


def _chat_request(
    *, provider: str, base_url: str, api_version: str, api_key: str, model: str
) -> tuple[str, dict[str, str], dict]:
    """Build the minimal chat-completion request for a provider."""
    endpoint = base_url.rstrip("/")
    if provider in AZURE_PROVIDERS:
        url = f"{endpoint}/openai/deployments/{model}/chat/completions"
        headers = {"api-key": api_key, "Content-Type": "application/json"}
        params = {"api-version": api_version.strip() or "2024-10-21"}
    else:
        url = f"{endpoint}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        params = {}
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "stream": False,
    }
    return url, headers, {"json": body, "params": params}


async def _chat_ping(
    *,
    provider: str,
    base_url: str,
    api_version: str,
    api_key: str,
    model: str,
    transport: httpx.AsyncBaseTransport | None,
) -> tuple[int | None, str]:
    url, headers, options = _chat_request(
        provider=provider,
        base_url=base_url,
        api_version=api_version,
        api_key=api_key,
        model=model,
    )
    try:
        async with httpx.AsyncClient(
            timeout=VALIDATION_TIMEOUT_SECONDS,
            transport=transport,
            follow_redirects=False,
        ) as client:
            response = await client.post(url, headers=headers, **options)
    except httpx.TimeoutException:
        return None, "The provider did not respond in time"
    except httpx.HTTPError:
        return None, "Could not reach the provider"
    if 200 <= response.status_code < 300:
        return response.status_code, "The endpoint, API key and model responded"
    if response.status_code in (401, 403):
        return response.status_code, (
            f"The provider rejected the API key (HTTP {response.status_code})"
        )
    return response.status_code, f"The provider returned HTTP {response.status_code}"


async def validate_model_config(
    *,
    provider: str,
    base_url: str,
    api_version: str,
    api_key: str | None,
    model: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[bool, str]:
    """Return ``(valid, message)`` for a provider/model/API-key combination."""
    cleaned_model = (model or "").strip()
    if not cleaned_model:
        return False, "Choose a model before validating"
    if not (api_key or "").strip():
        return False, "An API key is required for validation"

    provider_name = (provider or "openai").strip().lower()
    try:
        models = await discover_models(
            provider=provider_name,
            base_url=base_url,
            api_version=api_version,
            api_key=api_key,
            transport=transport,
        )
    except ExternalServiceError:
        models = []
    if models and cleaned_model in models:
        LOGGER.info("validated %s model %s via model listing", provider_name, cleaned_model)
        return True, f"Model {cleaned_model!r} is available from the provider"

    status, message = await _chat_ping(
        provider=provider_name,
        base_url=base_url,
        api_version=api_version,
        api_key=str(api_key),
        model=cleaned_model,
        transport=transport,
    )
    valid = status is not None and 200 <= status < 300
    LOGGER.info("validated %s model %s via chat ping: %s", provider_name, cleaned_model, valid)
    return valid, message

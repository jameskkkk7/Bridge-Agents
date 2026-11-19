"""Optional provider-backed moderation for the sanitize node.

The local banned-word list is always the hard gate. This module adds adapters for
mainstream content-safety APIs:

* ``openai`` — any OpenAI-compatible ``POST /v1/moderations`` endpoint
* ``azure`` — Azure AI Content Safety ``text:analyze``
* ``perspective`` — Google Jigsaw Perspective ``comments:analyze``

Credentials stay in the environment; only non-secret provider settings are
stored in the graph configuration.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

import httpx

LOGGER = logging.getLogger(__name__)

AZURE_CATEGORIES = ("Hate", "Sexual", "SelfHarm", "Violence")


class ModerationError(RuntimeError):
    """The configured moderation provider could not return a verdict."""


@dataclass(frozen=True)
class ModerationVerdict:
    """Provider verdict for one piece of text."""

    flagged: bool
    categories: Mapping[str, bool] = field(default_factory=dict)
    reason: str = ""


class Moderator(Protocol):
    """Anything that can classify text as safe or flagged."""

    async def check(self, text: str) -> ModerationVerdict: ...


async def _post_response(
    *,
    url: str,
    body: dict,
    headers: dict[str, str],
    timeout: float,
    transport: httpx.AsyncBaseTransport | None,
    params: dict[str, str] | None = None,
) -> dict:
    try:
        async with httpx.AsyncClient(timeout=max(0.5, timeout), transport=transport) as client:
            response = await client.post(url, json=body, headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ModerationError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise ModerationError("moderation endpoint returned an invalid payload")
    return payload


class OpenAICompatibleModerator:
    """Call ``POST {base_url}/moderations`` on an OpenAI-compatible provider."""

    name = "openai"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        model: str = "omni-moderation-latest",
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model or "omni-moderation-latest"
        self._timeout = max(0.5, timeout)
        self._transport = transport

    async def check(self, text: str) -> ModerationVerdict:
        """Return the provider verdict for ``text``."""
        if not text.strip():
            return ModerationVerdict(flagged=False)
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = await _post_response(
            url=f"{self._base_url}/moderations",
            body={"model": self._model, "input": text},
            headers=headers,
            timeout=self._timeout,
            transport=self._transport,
        )
        results = payload.get("results")
        if not isinstance(results, list) or not results:
            raise ModerationError("moderation endpoint returned no results")
        first = results[0] if isinstance(results[0], dict) else {}
        categories = {
            str(name): True for name, value in (first.get("categories") or {}).items() if value
        }
        flagged = bool(first.get("flagged"))
        reason = ", ".join(categories) or ("flagged" if flagged else "")
        return ModerationVerdict(flagged=flagged, categories=categories, reason=reason)


class AzureContentSafetyModerator:
    """Call Azure AI Content Safety ``contentsafety/text:analyze``."""

    name = "azure"

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        api_version: str = "2024-09-01",
        severity_threshold: int = 2,
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._api_version = api_version or "2024-09-01"
        self._severity_threshold = max(0, min(7, severity_threshold))
        self._timeout = max(0.5, timeout)
        self._transport = transport

    async def check(self, text: str) -> ModerationVerdict:
        if not text.strip():
            return ModerationVerdict(flagged=False)
        payload = await _post_response(
            url=f"{self._endpoint}/contentsafety/text:analyze",
            body={
                "text": text,
                "categories": list(AZURE_CATEGORIES),
                "outputType": "FourSeverityLevels",
            },
            headers={
                "Content-Type": "application/json",
                "Ocp-Apim-Subscription-Key": self._api_key,
            },
            params={"api-version": self._api_version},
            timeout=self._timeout,
            transport=self._transport,
        )
        analysis = payload.get("categoriesAnalysis")
        if not isinstance(analysis, list):
            raise ModerationError("Azure Content Safety returned no categoriesAnalysis")
        severity_by_category: dict[str, int] = {}
        for entry in analysis:
            if not isinstance(entry, dict):
                continue
            category = str(entry.get("category") or "")
            try:
                severity = int(entry.get("severity") or 0)
            except (TypeError, ValueError):
                severity = 0
            severity_by_category[category] = severity
        flagged_categories = {
            category: True
            for category, severity in severity_by_category.items()
            if severity >= self._severity_threshold
        }
        flagged = bool(flagged_categories)
        reason = ", ".join(
            f"{category}={severity}"
            for category, severity in severity_by_category.items()
            if severity >= self._severity_threshold
        )
        return ModerationVerdict(
            flagged=flagged,
            categories=flagged_categories,
            reason=reason,
        )


class PerspectiveModerator:
    """Call Google Jigsaw Perspective ``comments:analyze`` (toxicity)."""

    name = "perspective"

    DEFAULT_ENDPOINT = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"

    def __init__(
        self,
        *,
        endpoint: str = "",
        api_key: str,
        threshold: float = 0.7,
        language: str = "en",
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._endpoint = (endpoint or self.DEFAULT_ENDPOINT).rstrip("/")
        self._api_key = api_key
        self._threshold = max(0.0, min(1.0, threshold))
        self._language = language or "en"
        self._timeout = max(0.5, timeout)
        self._transport = transport

    async def check(self, text: str) -> ModerationVerdict:
        if not text.strip():
            return ModerationVerdict(flagged=False)
        payload = await _post_response(
            url=self._endpoint,
            body={
                "comment": {"text": text},
                "languages": [self._language],
                "requestedAttributes": {"TOXICITY": {}},
            },
            headers={"Content-Type": "application/json"},
            params={"key": self._api_key},
            timeout=self._timeout,
            transport=self._transport,
        )
        scores = payload.get("attributeScores")
        if not isinstance(scores, dict):
            raise ModerationError("Perspective returned no attributeScores")
        toxicity = scores.get("TOXICITY")
        summary = toxicity.get("summaryScore") if isinstance(toxicity, dict) else None
        try:
            score = float((summary or {}).get("value", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        flagged = score >= self._threshold
        return ModerationVerdict(
            flagged=flagged,
            categories={"TOXICITY": flagged},
            reason=f"TOXICITY={score:.2f}",
        )


PROVIDERS = ("openai", "azure", "perspective")


def create_moderator(
    provider: str,
    *,
    base_url: str = "",
    api_key: str = "",
    model: str = "omni-moderation-latest",
    timeout: float = 5.0,
    transport: httpx.AsyncBaseTransport | None = None,
    api_version: str = "",
    severity_threshold: int = 2,
    threshold: float = 0.7,
    language: str = "en",
) -> Moderator:
    """Build the configured provider adapter.

    Raises ``ValueError`` for an unknown provider name so callers can log it and
    fall back to the local hard gate.
    """
    normalized = (provider or "openai").strip().lower()
    if normalized in ("openai", "openai-compatible", "openai_compatible"):
        return OpenAICompatibleModerator(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=timeout,
            transport=transport,
        )
    if normalized in ("azure", "azure-content-safety", "azure_content_safety"):
        return AzureContentSafetyModerator(
            endpoint=base_url,
            api_key=api_key,
            api_version=api_version or "2024-09-01",
            severity_threshold=severity_threshold,
            timeout=timeout,
            transport=transport,
        )
    if normalized in ("perspective", "google-perspective", "jigsaw"):
        return PerspectiveModerator(
            endpoint=base_url,
            api_key=api_key,
            threshold=threshold,
            language=language,
            timeout=timeout,
            transport=transport,
        )
    raise ValueError(f"unknown moderation provider: {provider}")

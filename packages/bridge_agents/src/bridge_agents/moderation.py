"""Optional provider-backed moderation for the sanitize node.

The local banned-word list is always the hard gate. This module adds a
best-effort call to an OpenAI-compatible ``/v1/moderations`` endpoint so
deployments can also use the same provider-side classifier as their model.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

import httpx

LOGGER = logging.getLogger(__name__)


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


class OpenAICompatibleModerator:
    """Call ``POST {base_url}/moderations`` on an OpenAI-compatible provider."""

    name = "openai-compatible"

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
        """Return the provider verdict for ``text``.

        Raises :class:`ModerationError` for transport, HTTP and payload errors;
        the sanitize node decides whether to fail open or closed.
        """
        if not text.strip():
            return ModerationVerdict(flagged=False)
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/moderations",
                    json={"model": self._model, "input": text},
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ModerationError(str(exc)) from exc

        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list) or not results:
            raise ModerationError("moderation endpoint returned no results")
        first = results[0] if isinstance(results[0], dict) else {}
        categories = {
            str(name): True for name, value in (first.get("categories") or {}).items() if value
        }
        flagged = bool(first.get("flagged"))
        reason = ", ".join(categories) or ("flagged" if flagged else "")
        return ModerationVerdict(flagged=flagged, categories=categories, reason=reason)

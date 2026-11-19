"""Optional provider-backed moderation for the sanitize node.

The local banned-word list is always the hard gate. This module adds adapters for
mainstream content-safety APIs:

* ``openai`` — any OpenAI-compatible ``POST /v1/moderations`` endpoint
* ``azure`` — Azure AI Content Safety ``text:analyze``
* ``perspective`` — Google Jigsaw Perspective ``comments:analyze``
* ``aliyun`` — Alibaba Cloud Content Moderation ``TextModeration``
* ``tencent`` — Tencent Cloud TMS ``TextModeration``

Credentials stay in the environment; only non-secret provider settings are
stored in the graph configuration. Responses are validated defensively: a
provider that is unreachable **or** returns an unexpected payload raises
``ModerationError`` so the sanitize node can apply its fail-open/fail-closed
policy instead of crashing the conversation. Providers with a documented text
length limit are asked in chunks so long replies are still classified in full.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import math
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx

from bridge_agents.config import Settings

LOGGER = logging.getLogger(__name__)

AZURE_CATEGORIES = ("Hate", "Sexual", "SelfHarm", "Violence")

# Documented per-request text limits of the upstream APIs.
AZURE_MAX_TEXT_CHARS = 10_000
ALIYUN_MAX_TEXT_CHARS = 600
TENCENT_MAX_TEXT_CHARS = 10_000

PERSPECTIVE_DEFAULT_ENDPOINT = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
TENCENT_DEFAULT_ENDPOINT = "https://tms.tencentcloudapi.com"

_ALIYUN_SAFE_LABELS = frozenset({"normal", "pass"})
# Safety net against a pathological reply turning one check into hundreds of
# serial provider calls; the policy (fail open/closed) then applies as usual.
MAX_MODERATION_CHUNKS = 64
# Hard ceiling for one check, on top of the per-request timeout.
MAX_TOTAL_MODERATION_SECONDS = 120.0
_TRUE_VALUES = frozenset({"true", "1", "yes", "on"})
_FALSE_VALUES = frozenset({"false", "0", "no", "off"})
_PROVIDER_ALIASES = {
    "openai": "openai",
    "openai-compatible": "openai",
    "openai_compatible": "openai",
    "azure": "azure",
    "azure-content-safety": "azure",
    "azure_content_safety": "azure",
    "perspective": "perspective",
    "google-perspective": "perspective",
    "jigsaw": "perspective",
    "aliyun": "aliyun",
    "alibaba": "aliyun",
    "aliyun-green": "aliyun",
    "green": "aliyun",
    "tencent": "tencent",
    "tms": "tencent",
    "tencent-tms": "tencent",
}
PROVIDERS = ("openai", "azure", "perspective", "aliyun", "tencent")

# Redact query-string credentials (e.g. the Perspective ``?key=``) before a URL
# can reach a log line or an exception message.
_SECRET_QUERY_RE = re.compile(
    r"([?&](?:key|api[_-]?key|token|access[_-]?token|secret|signature)=)[^&\s\"']+",
    re.IGNORECASE,
)


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


class UnavailableModerator:
    """Placeholder for an enabled provider that could not be configured.

    Keeping a non-``None`` moderator means the sanitize node always applies its
    configured fail-open/fail-closed policy instead of silently skipping the
    provider step when credentials or a URL are missing.
    """

    name = "unavailable"

    def __init__(self, reason: str) -> None:
        self._reason = reason or "provider moderation is not configured"

    async def check(self, text: str) -> ModerationVerdict:
        raise ModerationError(self._reason)


# -- configuration helpers ---------------------------------------------------


def redact_secret_urls(text: str) -> str:
    """Remove query-string credentials from text before logging it."""
    return _SECRET_QUERY_RE.sub(r"\1***", text)


def parse_bool_setting(value: object) -> bool | None:
    """Parse a permissive boolean; ``None`` means the value is not usable."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value) if value in (0, 1) else None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_VALUES:
            return True
        if normalized in _FALSE_VALUES:
            return False
    return None


def clamp_number(value: float, *, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return min(maximum, max(minimum, value))


def canonical_provider(provider: object) -> str | None:
    """Return the canonical provider name (or ``None`` when unknown)."""
    return _PROVIDER_ALIASES.get(str(provider or "").strip().lower())


def _normalize_host(host: object) -> str:
    """Normalise a hostname for allow-list comparison (IDNA, brackets, port)."""
    cleaned = str(host or "").strip().lower()
    if not cleaned:
        return ""
    if cleaned.startswith("[") and "]" in cleaned:
        return cleaned[1 : cleaned.index("]")].lower()
    if cleaned.count(":") == 1:
        # allow-list entries may be written as "host:port"
        try:
            parsed = urlsplit(f"//{cleaned}")
            if parsed.hostname:
                cleaned = parsed.hostname.lower()
        except ValueError:
            pass
    cleaned = cleaned.rstrip(".")
    try:
        return cleaned.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return cleaned.lower()


def validate_moderation_base_url(url: str) -> str:
    """Validate an http(s) base URL and return it stripped.

    Invalid ports would otherwise surface as ``httpx.InvalidURL`` at request
    time (which is neither ``httpx.HTTPError`` nor ``ValueError``) and embedded
    userinfo would smuggle credentials into the stored graph configuration.
    """
    cleaned = str(url or "").strip()
    if not cleaned:
        raise ValueError("moderation provider URL must not be empty")
    if any(char.isspace() for char in cleaned):
        raise ValueError("moderation provider URL must not contain whitespace")
    try:
        split = urlsplit(cleaned)
        hostname = split.hostname
    except ValueError as exc:
        raise ValueError("moderation provider URL is not a valid URL") from exc
    if split.scheme not in ("http", "https"):
        raise ValueError("moderation provider URL must use http or https")
    if not hostname:
        raise ValueError("moderation provider URL must include a host")
    if split.username or split.password:
        raise ValueError("moderation provider URL must not contain credentials")
    if split.query or split.fragment:
        raise ValueError("moderation provider URL must not contain a query or fragment")
    try:
        _ = split.port
    except ValueError as exc:
        raise ValueError("moderation provider URL has an invalid port") from exc
    return cleaned


def _allowed_hosts(settings: Settings) -> set[str]:
    raw = getattr(settings, "moderation_allowed_host_list", None) or []
    return {normalized for item in raw if (normalized := _normalize_host(item))}


def _ensure_allowed_host(url: str, settings: Settings) -> None:
    allowed = _allowed_hosts(settings)
    if not allowed:
        return
    host = _normalize_host(urlsplit(url).hostname)
    if host not in allowed:
        raise ValueError(f"moderation host {host!r} is not listed in MODERATION_ALLOWED_HOSTS")


def resolve_provider_base_url(provider: str, config: Mapping, settings: Settings) -> str:
    """Resolve, validate and allow-list the endpoint a provider will be called at."""
    override = config.get("provider_base_url")
    override_text = str(override).strip() if override not in (None, "") else ""
    if provider == "azure":
        candidate = override_text or str(settings.moderation_azure_endpoint or "").strip()
    elif provider == "perspective":
        candidate = override_text or PERSPECTIVE_DEFAULT_ENDPOINT
    elif provider == "aliyun":
        region = str(
            config.get("provider_region") or settings.moderation_aliyun_region or "cn-shanghai"
        ).strip()
        candidate = (
            override_text
            or str(settings.moderation_aliyun_endpoint or "").strip()
            or f"https://green-cip.{region}.aliyuncs.com"
        )
    elif provider == "tencent":
        candidate = (
            override_text
            or str(settings.moderation_tencent_endpoint or "").strip()
            or TENCENT_DEFAULT_ENDPOINT
        )
    elif provider == "openai":
        candidate = (
            override_text
            or str(settings.moderation_base_url or "").strip()
            or str(settings.openai_base_url or "").strip()
        )
    else:  # pragma: no cover - callers canonicalise the provider first
        raise ValueError(f"unknown moderation provider: {provider!r}")
    if not candidate:
        raise ValueError(f"{provider} moderation endpoint is not configured")
    normalized = validate_moderation_base_url(candidate)
    _ensure_allowed_host(normalized, settings)
    return normalized


def provider_credentials_error(provider: str, settings: Settings) -> str | None:
    """Return the missing credential variable for a provider, if any.

    Azure and Perspective intentionally do not fall back to the generic
    ``MODERATION_API_KEY``: that key belongs to the OpenAI-compatible adapter and
    reusing it would send one vendor's secret to another vendor.
    """
    if provider == "azure":
        if not settings.moderation_azure_key:
            return "MODERATION_AZURE_KEY is not configured"
    elif provider == "perspective":
        if not settings.moderation_perspective_key:
            return "MODERATION_PERSPECTIVE_KEY is not configured"
    elif provider == "aliyun":
        if not settings.moderation_aliyun_access_key_id:
            return "MODERATION_ALIYUN_ACCESS_KEY_ID is not configured"
        if not settings.moderation_aliyun_access_key_secret:
            return "MODERATION_ALIYUN_ACCESS_KEY_SECRET is not configured"
    elif provider == "tencent":
        if not settings.moderation_tencent_secret_id:
            return "MODERATION_TENCENT_SECRET_ID is not configured"
        if not settings.moderation_tencent_secret_key:
            return "MODERATION_TENCENT_SECRET_KEY is not configured"
    return None


def _number_setting(
    value: object,
    fallback: object,
    *,
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    try:
        parsed = float(value) if value is not None else float(fallback)
    except (TypeError, ValueError):
        parsed = _as_number(fallback)
        if parsed is None:
            parsed = float(minimum)
    clamped = clamp_number(parsed, minimum=minimum, maximum=maximum)
    if clamped != parsed:
        LOGGER.warning(
            "sanitize node: %s=%s is outside %.2f..%.2f; using %.2f",
            name,
            parsed,
            minimum,
            maximum,
            clamped,
        )
    return clamped


def _int_setting(
    value: object,
    fallback: object,
    *,
    name: str,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value) if value is not None else int(fallback)
    except (TypeError, ValueError):
        parsed = _as_int(fallback)
        if parsed is None:
            parsed = minimum
    clamped = clamp_int(parsed, minimum=minimum, maximum=maximum)
    if clamped != parsed:
        LOGGER.warning(
            "sanitize node: %s=%s is outside %d..%d; using %d",
            name,
            parsed,
            minimum,
            maximum,
            clamped,
        )
    return clamped


def _as_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: object) -> int | None:
    parsed = _as_number(value)
    if parsed is None or not parsed.is_integer():
        return None
    return int(parsed)


def validate_sanitize_provider_config(config: Mapping) -> str | None:
    """Validate the provider keys of one sanitize node config.

    The check is pure: it validates stored values (types, ranges, URL shape) and
    never looks at the environment. Returns an error message or ``None``.
    """
    enabled = parse_bool_setting(config.get("provider_enabled"))
    if config.get("provider_enabled") is not None and enabled is None:
        return "provider_enabled must be true or false"
    if not enabled:
        return None
    raw_provider = config.get("provider")
    if raw_provider not in (None, ""):
        if not isinstance(raw_provider, str):
            return "provider must be a string"
        if canonical_provider(raw_provider) is None:
            return f"unknown moderation provider: {raw_provider!r}"
    if config.get("provider_fail_open") is not None:
        if parse_bool_setting(config.get("provider_fail_open")) is None:
            return "provider_fail_open must be true or false"
    fallback = config.get("provider_fallback")
    if fallback is not None and not isinstance(fallback, str):
        return "provider_fallback must be a string"
    for key in (
        "provider_model",
        "provider_api_version",
        "provider_language",
        "provider_region",
        "provider_service",
        "provider_biz_type",
    ):
        value = config.get(key)
        if value is not None and not isinstance(value, str):
            return f"{key} must be a string"
    if config.get("provider_timeout") is not None:
        timeout = _as_number(config.get("provider_timeout"))
        if timeout is None:
            return "provider_timeout must be a number"
        if not 0.5 <= timeout <= 30:
            return "provider_timeout must be between 0.5 and 30 seconds"
    if config.get("provider_severity") is not None:
        severity = _as_int(config.get("provider_severity"))
        if severity is None:
            return "provider_severity must be an integer"
        if not 1 <= severity <= 7:
            return "provider_severity must be between 1 and 7 (0 would flag every reply)"
    if config.get("provider_threshold") is not None:
        threshold = _as_number(config.get("provider_threshold"))
        if threshold is None:
            return "provider_threshold must be a number"
        if not 0.01 <= threshold <= 1:
            return "provider_threshold must be between 0.01 and 1 (0 would flag every reply)"
    base_url = config.get("provider_base_url")
    if base_url not in (None, ""):
        if not isinstance(base_url, str):
            return "provider_base_url must be a string"
        try:
            validate_moderation_base_url(base_url)
        except ValueError as exc:
            return str(exc)
    return None


def build_configured_moderator(
    provider: str,
    config: Mapping,
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Moderator:
    """Build the adapter for ``provider`` from graph config plus environment.

    Raises ``ValueError`` with an actionable message when the provider cannot be
    configured (missing credential, invalid endpoint, host not allow-listed).
    """
    missing = provider_credentials_error(provider, settings)
    if missing:
        raise ValueError(missing)
    base_url = resolve_provider_base_url(provider, config, settings)
    timeout = _number_setting(
        config.get("provider_timeout"),
        settings.moderation_timeout,
        name="provider_timeout",
        minimum=0.5,
        maximum=30.0,
    )
    if provider == "openai":
        return create_moderator(
            "openai",
            base_url=base_url,
            api_key=str(settings.moderation_api_key or settings.openai_api_key or ""),
            model=str(config.get("provider_model") or settings.moderation_model),
            timeout=timeout,
            transport=transport,
        )
    if provider == "azure":
        return create_moderator(
            "azure",
            base_url=base_url,
            api_key=str(settings.moderation_azure_key),
            api_version=str(
                config.get("provider_api_version") or settings.moderation_azure_api_version
            ),
            severity_threshold=_int_setting(
                config.get("provider_severity"),
                settings.moderation_azure_severity,
                name="provider_severity",
                minimum=1,
                maximum=7,
            ),
            timeout=timeout,
            transport=transport,
        )
    if provider == "perspective":
        return create_moderator(
            "perspective",
            base_url=base_url,
            api_key=str(settings.moderation_perspective_key),
            threshold=_number_setting(
                config.get("provider_threshold"),
                settings.moderation_perspective_threshold,
                name="provider_threshold",
                minimum=0.01,
                maximum=1.0,
            ),
            language=str(config.get("provider_language") or "en"),
            timeout=timeout,
            transport=transport,
        )
    if provider == "aliyun":
        region = str(
            config.get("provider_region") or settings.moderation_aliyun_region or "cn-shanghai"
        ).strip()
        return create_moderator(
            "aliyun",
            base_url=base_url,
            access_key_id=str(settings.moderation_aliyun_access_key_id),
            access_key_secret=str(settings.moderation_aliyun_access_key_secret),
            region=region,
            service=str(config.get("provider_service") or settings.moderation_aliyun_service),
            timeout=timeout,
            transport=transport,
        )
    if provider == "tencent":
        region = str(
            config.get("provider_region") or settings.moderation_tencent_region or "ap-guangzhou"
        ).strip()
        return create_moderator(
            "tencent",
            base_url=base_url,
            access_key_id=str(settings.moderation_tencent_secret_id),
            access_key_secret=str(settings.moderation_tencent_secret_key),
            region=region,
            biz_type=str(config.get("provider_biz_type") or settings.moderation_tencent_biz_type),
            timeout=timeout,
            transport=transport,
        )
    raise ValueError(f"unknown moderation provider: {provider!r}")  # pragma: no cover


# -- transport helpers -------------------------------------------------------


async def _post_json(
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
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
        raise ModerationError(redact_secret_urls(str(exc))) from exc
    if not isinstance(payload, dict):
        raise ModerationError("moderation endpoint returned an invalid payload")
    return payload


async def _post_form(
    *,
    url: str,
    form: dict[str, str],
    timeout: float,
    transport: httpx.AsyncBaseTransport | None,
) -> dict:
    try:
        async with httpx.AsyncClient(timeout=max(0.5, timeout), transport=transport) as client:
            response = await client.post(url, data=form)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
        raise ModerationError(redact_secret_urls(str(exc))) from exc
    if not isinstance(payload, dict):
        raise ModerationError("moderation endpoint returned an invalid payload")
    return payload


async def _post_content(
    *,
    url: str,
    content: bytes,
    headers: dict[str, str],
    timeout: float,
    transport: httpx.AsyncBaseTransport | None,
) -> dict:
    try:
        async with httpx.AsyncClient(timeout=max(0.5, timeout), transport=transport) as client:
            response = await client.post(url, content=content, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
        raise ModerationError(redact_secret_urls(str(exc))) from exc
    if not isinstance(payload, dict):
        raise ModerationError("moderation endpoint returned an invalid payload")
    return payload


def _as_mapping(value: object, source: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise ModerationError(f"{source} returned an invalid payload")
    return value


def _coerce_bool(value: object, source: str) -> bool:
    if isinstance(value, float) and math.isnan(value):
        raise ModerationError(f"{source} returned an invalid numeric value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Some OpenAI-compatible endpoints return category probabilities.
        return value != 0
    parsed = parse_bool_setting(value)
    if parsed is None:
        raise ModerationError(f"{source} returned an invalid boolean value")
    return parsed


def _split_text(text: str, limit: int) -> list[str]:
    """Split text into chunks no longer than ``limit`` characters.

    Splits prefer a newline or space near the boundary; a hard cut is used when
    the remainder is dominated by one long token.
    """
    if limit <= 0:  # pragma: no cover - constants are always positive
        raise ValueError("limit must be positive")
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = max(window.rfind("\n"), window.rfind(" "))
        cut = cut + 1 if cut >= limit // 2 else limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        chunks.append(remaining)
    return chunks


def _request_chunks(text: str, limit: int, *, provider: str) -> list[str]:
    """Split text for a provider request, refusing pathological chunk counts."""
    chunks = _split_text(text, limit)
    if len(chunks) > MAX_MODERATION_CHUNKS:
        raise ModerationError(
            f"{provider} reply is too long to moderate safely ({len(chunks)} chunks)"
        )
    return chunks


# -- adapters ----------------------------------------------------------------


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
        self._base_url = validate_moderation_base_url(base_url).rstrip("/")
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
        payload = await _post_json(
            url=f"{self._base_url}/moderations",
            body={"model": self._model, "input": text},
            headers=headers,
            timeout=self._timeout,
            transport=self._transport,
        )
        results = payload.get("results")
        if not isinstance(results, list) or not results:
            raise ModerationError("moderation endpoint returned no results")
        first = results[0]
        if not isinstance(first, Mapping):
            raise ModerationError("moderation endpoint returned an invalid result object")
        categories: dict[str, bool] = {}
        raw_categories = first.get("categories")
        if raw_categories is not None:
            if not isinstance(raw_categories, Mapping):
                raise ModerationError("moderation endpoint returned invalid categories")
            for name, value in raw_categories.items():
                if _coerce_bool(value, "OpenAI-compatible moderation categories"):
                    categories[str(name)] = True
        raw_flagged = first.get("flagged")
        if raw_flagged is not None:
            flagged = _coerce_bool(raw_flagged, "OpenAI-compatible moderation result")
        elif raw_categories is not None:
            flagged = bool(categories)
        else:
            raise ModerationError("moderation endpoint returned neither flagged nor categories")
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
        self._endpoint = validate_moderation_base_url(endpoint).rstrip("/")
        self._api_key = api_key
        self._api_version = api_version or "2024-09-01"
        self._severity_threshold = _int_setting(
            severity_threshold,
            severity_threshold,
            name="severity_threshold",
            minimum=1,
            maximum=7,
        )
        self._timeout = max(0.5, timeout)
        self._transport = transport

    async def check(self, text: str) -> ModerationVerdict:
        if not text.strip():
            return ModerationVerdict(flagged=False)
        chunks = _request_chunks(text, AZURE_MAX_TEXT_CHARS, provider="Azure")
        if len(chunks) > 1:
            LOGGER.info(
                "Azure moderation split a %d character reply into %d requests",
                len(text),
                len(chunks),
            )
        flagged = False
        categories: dict[str, bool] = {}
        reasons: list[str] = []
        loop = asyncio.get_running_loop()
        budget = min(self._timeout * len(chunks), MAX_TOTAL_MODERATION_SECONDS)
        deadline = loop.time() + budget
        for chunk in chunks:
            remaining = deadline - loop.time()
            if remaining < 0.5:
                raise ModerationError("Azure moderation exceeded the configured timeout")
            verdict = await self._check_chunk(chunk, timeout=min(remaining, self._timeout))
            flagged = flagged or verdict.flagged
            categories.update(verdict.categories)
            if verdict.flagged and verdict.reason:
                reasons.append(verdict.reason)
        return ModerationVerdict(
            flagged=flagged,
            categories=categories,
            reason="; ".join(reasons),
        )

    async def _check_chunk(self, text: str, *, timeout: float) -> ModerationVerdict:
        payload = await _post_json(
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
            timeout=timeout,
            transport=self._transport,
        )
        analysis = payload.get("categoriesAnalysis")
        if not isinstance(analysis, list):
            raise ModerationError("Azure Content Safety returned no categoriesAnalysis")
        severity_by_category: dict[str, int] = {}
        for entry in analysis:
            if not isinstance(entry, Mapping):
                continue
            category = str(entry.get("category") or "").strip()
            if category not in AZURE_CATEGORIES:
                continue
            try:
                severity = int(entry.get("severity") or 0)
            except (TypeError, ValueError):
                severity = 0
            severity = max(severity, severity_by_category.get(category, 0))
            severity_by_category[category] = severity
        if not severity_by_category:
            raise ModerationError("Azure Content Safety returned no recognized categories")
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
    DEFAULT_ENDPOINT = PERSPECTIVE_DEFAULT_ENDPOINT

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
        self._endpoint = validate_moderation_base_url(endpoint or self.DEFAULT_ENDPOINT).rstrip("/")
        self._api_key = api_key
        self._threshold = _number_setting(
            threshold,
            threshold,
            name="threshold",
            minimum=0.01,
            maximum=1.0,
        )
        self._language = language or "en"
        self._timeout = max(0.5, timeout)
        self._transport = transport

    async def check(self, text: str) -> ModerationVerdict:
        if not text.strip():
            return ModerationVerdict(flagged=False)
        payload = await _post_json(
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
        if not isinstance(scores, Mapping):
            raise ModerationError("Perspective returned no attributeScores")
        toxicity = scores.get("TOXICITY")
        if not isinstance(toxicity, Mapping):
            raise ModerationError("Perspective returned no TOXICITY score")
        summary = toxicity.get("summaryScore")
        if not isinstance(summary, Mapping):
            raise ModerationError("Perspective returned an invalid TOXICITY summary")
        try:
            score = float(summary["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ModerationError("Perspective returned an invalid toxicity value") from exc
        flagged = score >= self._threshold
        return ModerationVerdict(
            flagged=flagged,
            categories={"TOXICITY": flagged},
            reason=f"TOXICITY={score:.2f}",
        )


class AliyunTextModerationModerator:
    """Call Alibaba Cloud Content Moderation ``TextModeration`` (2022-03-02).

    Uses the RPC-style HMAC-SHA1 signature documented for Alibaba Cloud
    OpenAPI. Endpoint: ``https://green-cip.{region}.aliyuncs.com``. The API
    accepts at most 600 characters per request, so long replies are split.
    """

    name = "aliyun"

    def __init__(
        self,
        *,
        endpoint: str,
        access_key_id: str,
        access_key_secret: str,
        service: str = "comment_detection",
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
        timestamp: str | None = None,
        nonce: str | None = None,
    ) -> None:
        self._endpoint = validate_moderation_base_url(endpoint).rstrip("/") + "/"
        self._access_key_id = access_key_id
        self._access_key_secret = access_key_secret
        self._service = service or "comment_detection"
        self._timeout = max(0.5, timeout)
        self._transport = transport
        self._timestamp = timestamp
        self._nonce = nonce

    async def check(self, text: str) -> ModerationVerdict:
        if not text.strip():
            return ModerationVerdict(flagged=False)
        chunks = _request_chunks(text, ALIYUN_MAX_TEXT_CHARS, provider="Alibaba Cloud")
        if len(chunks) > 1:
            LOGGER.info(
                "Alibaba Cloud moderation split a %d character reply into %d requests",
                len(text),
                len(chunks),
            )
        flagged = False
        categories: dict[str, bool] = {}
        reasons: list[str] = []
        loop = asyncio.get_running_loop()
        budget = min(self._timeout * len(chunks), MAX_TOTAL_MODERATION_SECONDS)
        deadline = loop.time() + budget
        for chunk in chunks:
            remaining = deadline - loop.time()
            if remaining < 0.5:
                raise ModerationError("Alibaba Cloud moderation exceeded the configured timeout")
            verdict = await self._check_chunk(chunk, timeout=min(remaining, self._timeout))
            flagged = flagged or verdict.flagged
            categories.update(verdict.categories)
            if verdict.flagged and verdict.reason:
                reasons.append(verdict.reason)
        return ModerationVerdict(
            flagged=flagged,
            categories=categories,
            reason=", ".join(reasons),
        )

    async def _check_chunk(self, text: str, *, timeout: float) -> ModerationVerdict:
        params = {
            "AccessKeyId": self._access_key_id,
            "Action": "TextModeration",
            "Format": "JSON",
            "Service": self._service,
            "ServiceParameters": json.dumps({"content": text}, ensure_ascii=False),
            "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": self._nonce or uuid4().hex,
            "SignatureVersion": "1.0",
            "Timestamp": self._timestamp or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Version": "2022-03-02",
        }
        params["Signature"] = aliyun_rpc_signature("POST", params, self._access_key_secret)
        payload = await _post_form(
            url=self._endpoint,
            form=params,
            timeout=timeout,
            transport=self._transport,
        )
        code = payload.get("Code")
        try:
            code_int = int(code)
        except (TypeError, ValueError):
            code_int = 500
        if code_int != 200:
            raise ModerationError(str(payload.get("Message") or f"Alibaba Cloud code {code}"))
        data = payload.get("Data")
        if not isinstance(data, Mapping):
            raise ModerationError("Alibaba Cloud returned no Data")
        raw_labels = data.get("labels")
        if raw_labels is None:
            raise ModerationError("Alibaba Cloud returned no labels")
        labels = [label.strip().lower() for label in str(raw_labels).split(",") if label.strip()]
        flagged_labels = [label for label in labels if label not in _ALIYUN_SAFE_LABELS]
        categories = {label: True for label in flagged_labels}
        reason = ", ".join(flagged_labels)
        return ModerationVerdict(
            flagged=bool(flagged_labels),
            categories=categories,
            reason=reason,
        )


class TencentTextModerationModerator:
    """Call Tencent Cloud TMS ``TextModeration`` (2020-12-29).

    Implements the TC3-HMAC-SHA256 signature and sends the post body as
    ``application/json; charset=utf-8``. Content is limited to 10,000 characters
    per request, so longer replies are split.
    """

    name = "tencent"

    def __init__(
        self,
        *,
        endpoint: str = TENCENT_DEFAULT_ENDPOINT,
        secret_id: str,
        secret_key: str,
        region: str = "ap-guangzhou",
        biz_type: str = "",
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
        timestamp: int | None = None,
    ) -> None:
        self._endpoint = validate_moderation_base_url(endpoint or TENCENT_DEFAULT_ENDPOINT).rstrip(
            "/"
        )
        self._secret_id = secret_id
        self._secret_key = secret_key
        self._region = region
        self._biz_type = biz_type
        self._timeout = max(0.5, timeout)
        self._transport = transport
        self._timestamp = timestamp

    async def check(self, text: str) -> ModerationVerdict:
        if not text.strip():
            return ModerationVerdict(flagged=False)
        chunks = _request_chunks(text, TENCENT_MAX_TEXT_CHARS, provider="Tencent Cloud")
        if len(chunks) > 1:
            LOGGER.info(
                "Tencent Cloud moderation split a %d character reply into %d requests",
                len(text),
                len(chunks),
            )
        flagged = False
        categories: dict[str, bool] = {}
        reasons: list[str] = []
        loop = asyncio.get_running_loop()
        budget = min(self._timeout * len(chunks), MAX_TOTAL_MODERATION_SECONDS)
        deadline = loop.time() + budget
        for chunk in chunks:
            remaining = deadline - loop.time()
            if remaining < 0.5:
                raise ModerationError("Tencent Cloud moderation exceeded the configured timeout")
            verdict = await self._check_chunk(chunk, timeout=min(remaining, self._timeout))
            flagged = flagged or verdict.flagged
            categories.update(verdict.categories)
            if verdict.flagged and verdict.reason:
                reasons.append(verdict.reason)
        return ModerationVerdict(
            flagged=flagged,
            categories=categories,
            reason="; ".join(reasons),
        )

    async def _check_chunk(self, text: str, *, timeout: float) -> ModerationVerdict:
        payload: dict[str, str] = {
            "Content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        }
        if self._biz_type:
            payload["BizType"] = self._biz_type
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        host = urlsplit(self._endpoint).netloc
        headers = tencent_tc3_headers(
            secret_id=self._secret_id,
            secret_key=self._secret_key,
            host=host,
            action="TextModeration",
            version="2020-12-29",
            region=self._region,
            payload=body,
            timestamp=self._timestamp,
        )
        payload_data = await _post_content(
            url=self._endpoint,
            content=body,
            headers=headers,
            timeout=timeout,
            transport=self._transport,
        )
        data = payload_data.get("Response")
        if not isinstance(data, Mapping):
            raise ModerationError("Tencent Cloud returned no Response")
        error = data.get("Error")
        if isinstance(error, Mapping):
            raise ModerationError(
                f"{error.get('Code') or 'TencentCloudError'}: {error.get('Message') or ''}".strip()
            )
        suggestion = str(data.get("Suggestion") or "").strip()
        label = str(data.get("Label") or "").strip()
        if not suggestion and not label:
            raise ModerationError("Tencent Cloud returned neither Suggestion nor Label")
        flagged = suggestion.lower() in ("block", "review") or (
            bool(label) and label.lower() != "normal"
        )
        categories = {label: True} if flagged and label else {}
        try:
            score = int(data.get("Score") or 0)
        except (TypeError, ValueError):
            score = 0
        reason = ""
        if flagged:
            reason = f"{label or 'flagged'} suggestion={suggestion or 'unknown'} score={score}"
        return ModerationVerdict(flagged=flagged, categories=categories, reason=reason)


def _percent_encode(value: str) -> str:
    """RFC 3986 encoding used by Alibaba Cloud RPC signatures."""
    return quote(str(value), safe="-_.~")


def aliyun_rpc_signature(method: str, params: dict[str, str], secret: str) -> str:
    """Compute the Alibaba Cloud RPC HMAC-SHA1 signature.

    Exposed for tests and for callers that need the exact signing behaviour.
    """
    canonical = "&".join(
        f"{_percent_encode(key)}={_percent_encode(params[key])}"
        for key in sorted(params)
        if key != "Signature"
    )
    string_to_sign = f"{method.upper()}&%2F&{_percent_encode(canonical)}"
    digest = hmac.new(
        f"{secret}&".encode(),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def tencent_tc3_headers(
    *,
    secret_id: str,
    secret_key: str,
    host: str,
    action: str,
    version: str,
    region: str,
    payload: bytes,
    timestamp: int | None = None,
    service: str = "tms",
) -> dict[str, str]:
    """Build the TC3-HMAC-SHA256 headers for a Tencent Cloud API request."""
    ts = int(timestamp if timestamp is not None else time.time())
    date = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")
    content_type = "application/json; charset=utf-8"
    canonical_headers = f"content-type:{content_type}\nhost:{host}\n"
    signed_headers = "content-type;host"
    hashed_payload = hashlib.sha256(payload).hexdigest()
    canonical_request = (
        "POST\n/\n\n" + canonical_headers + "\n" + signed_headers + "\n" + hashed_payload
    )
    scope = f"{date}/{service}/tc3_request"
    string_to_sign = (
        "TC3-HMAC-SHA256\n"
        f"{ts}\n"
        f"{scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    def _hmac(key: bytes, message: str) -> bytes:
        return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()

    secret_date = _hmac(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = _hmac(secret_date, service)
    secret_signing = _hmac(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {
        "Authorization": (
            f"TC3-HMAC-SHA256 Credential={secret_id}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
        "Content-Type": content_type,
        "Host": host,
        "X-TC-Action": action,
        "X-TC-Version": version,
        "X-TC-Timestamp": str(ts),
    }
    if region:
        headers["X-TC-Region"] = region
    return headers


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
    access_key_id: str = "",
    access_key_secret: str = "",
    region: str = "",
    service: str = "",
    biz_type: str = "",
) -> Moderator:
    """Build the configured provider adapter.

    Raises ``ValueError`` for an unknown provider name or an invalid endpoint so
    callers can log it and fall back to the local hard gate.
    """
    normalized = canonical_provider(provider)
    if normalized == "openai":
        return OpenAICompatibleModerator(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=timeout,
            transport=transport,
        )
    if normalized == "azure":
        return AzureContentSafetyModerator(
            endpoint=base_url,
            api_key=api_key,
            api_version=api_version or "2024-09-01",
            severity_threshold=severity_threshold,
            timeout=timeout,
            transport=transport,
        )
    if normalized == "perspective":
        return PerspectiveModerator(
            endpoint=base_url,
            api_key=api_key,
            threshold=threshold,
            language=language,
            timeout=timeout,
            transport=transport,
        )
    if normalized == "aliyun":
        return AliyunTextModerationModerator(
            endpoint=base_url or f"https://green-cip.{region or 'cn-shanghai'}.aliyuncs.com",
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            service=service or "comment_detection",
            timeout=timeout,
            transport=transport,
        )
    if normalized == "tencent":
        return TencentTextModerationModerator(
            endpoint=base_url or TENCENT_DEFAULT_ENDPOINT,
            secret_id=access_key_id,
            secret_key=access_key_secret,
            region=region or "ap-guangzhou",
            biz_type=biz_type,
            timeout=timeout,
            transport=transport,
        )
    raise ValueError(f"unknown moderation provider: {provider}")

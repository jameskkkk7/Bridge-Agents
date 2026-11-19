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

import base64
import hashlib
import hmac
import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote, urlsplit
from uuid import uuid4

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


class AliyunTextModerationModerator:
    """Call Alibaba Cloud Content Moderation ``TextModeration`` (2022-03-02).

    Uses the RPC-style HMAC-SHA1 signature documented for Alibaba Cloud
    OpenAPI. Endpoint: ``https://green-cip.{region}.aliyuncs.com``.
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
        self._endpoint = endpoint.rstrip("/") + "/"
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
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(self._endpoint, data=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ModerationError(str(exc)) from exc
        if not isinstance(payload, dict):
            raise ModerationError("Alibaba Cloud returned an invalid payload")
        code = payload.get("Code")
        try:
            code_int = int(code)
        except (TypeError, ValueError):
            code_int = 500
        if code_int != 200:
            raise ModerationError(str(payload.get("Message") or f"Alibaba Cloud code {code}"))
        data = payload.get("Data") or {}
        raw_labels = data.get("labels") if isinstance(data, dict) else None
        labels = [
            label.strip().lower() for label in str(raw_labels or "").split(",") if label.strip()
        ]
        flagged_labels = [label for label in labels if label not in ("normal", "pass")]
        categories = {label: True for label in flagged_labels}
        reason = ", ".join(flagged_labels) or (labels[0] if labels else "")
        return ModerationVerdict(
            flagged=bool(flagged_labels),
            categories=categories,
            reason=reason,
        )


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


class TencentTextModerationModerator:
    """Call Tencent Cloud TMS ``TextModeration`` (2020-12-29).

    Implements the TC3-HMAC-SHA256 signature and sends the post body as
    ``application/json; charset=utf-8``.
    """

    name = "tencent"

    def __init__(
        self,
        *,
        endpoint: str = "https://tms.tencentcloudapi.com",
        secret_id: str,
        secret_key: str,
        region: str = "ap-guangzhou",
        biz_type: str = "",
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
        timestamp: int | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/") or "https://tms.tencentcloudapi.com"
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
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(self._endpoint, content=body, headers=headers)
                response.raise_for_status()
                payload_data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ModerationError(str(exc)) from exc
        if not isinstance(payload_data, dict):
            raise ModerationError("Tencent Cloud returned an invalid payload")
        data = payload_data.get("Response")
        if not isinstance(data, dict):
            raise ModerationError("Tencent Cloud returned no Response")
        error = data.get("Error")
        if isinstance(error, dict):
            raise ModerationError(
                f"{error.get('Code') or 'TencentCloudError'}: {error.get('Message') or ''}".strip()
            )
        suggestion = str(data.get("Suggestion") or "").strip()
        label = str(data.get("Label") or "").strip()
        flagged = suggestion.lower() in ("block", "review") or (
            bool(label) and label.lower() != "normal"
        )
        categories = {label: True} if flagged and label else {}
        try:
            score = int(data.get("Score") or 0)
        except (TypeError, ValueError):
            score = 0
        reason = f"{label or 'flagged'} suggestion={suggestion or 'unknown'} score={score}"
        return ModerationVerdict(flagged=flagged, categories=categories, reason=reason)


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


PROVIDERS = ("openai", "azure", "perspective", "aliyun", "tencent")


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
    if normalized in ("aliyun", "alibaba", "aliyun-green", "green"):
        return AliyunTextModerationModerator(
            endpoint=base_url or f"https://green-cip.{region or 'cn-shanghai'}.aliyuncs.com",
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            service=service or "comment_detection",
            timeout=timeout,
            transport=transport,
        )
    if normalized in ("tencent", "tms", "tencent-tms"):
        return TencentTextModerationModerator(
            endpoint=base_url or "https://tms.tencentcloudapi.com",
            secret_id=access_key_id,
            secret_key=access_key_secret,
            region=region or "ap-guangzhou",
            biz_type=biz_type,
            timeout=timeout,
            transport=transport,
        )
    raise ValueError(f"unknown moderation provider: {provider}")

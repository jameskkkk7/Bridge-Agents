"""Runtime model configuration persisted in the settings table.

The environment defines defaults; this service lets an administrator override
the model endpoint, name, sampling settings and API key at runtime. The API key
is stored encrypted (Fernet, key derived from the deployment secret) and is
never returned by the API.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging

from bridge_agents.config import Settings
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.services.runtime_config_service import RuntimeConfigService

LOGGER = logging.getLogger(__name__)

MODEL_CONFIG_KEY = "model_runtime_config"
_SECRET_CONTEXT = "bridge-agents:model-config:v1"

# Fields that may be overridden at runtime.
_OVERRIDE_FIELDS = (
    "openai_base_url",
    "openai_model",
    "openai_temperature",
    "openai_timeout",
    "openai_max_retries",
    "openai_thinking_enabled",
)


def _fernet(settings: Settings) -> Fernet:
    digest = hashlib.sha256(f"{settings.jwt_secret}:{_SECRET_CONTEXT}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(settings: Settings, value: str) -> str:
    """Encrypt an API key for storage."""
    return _fernet(settings).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(settings: Settings, token: str) -> str | None:
    """Decrypt a stored API key; returns None when the token is unusable."""
    try:
        return _fernet(settings).decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        LOGGER.error("stored model API key could not be decrypted; ignoring it")
        return None


def _parse(raw: str) -> dict:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("The stored model configuration is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValidationError("The stored model configuration is not an object")
    return payload


async def load_override(
    db: AsyncSession, settings: Settings, *, include_secret: bool = False
) -> dict | None:
    """Return the persisted override, optionally with the decrypted API key."""
    raw = await RuntimeConfigService(db).get(MODEL_CONFIG_KEY)
    if not raw:
        return None
    payload = _parse(raw)
    override = {key: payload[key] for key in _OVERRIDE_FIELDS if key in payload}
    encrypted = payload.get("api_key_encrypted")
    if encrypted:
        if include_secret:
            decrypted = decrypt_secret(settings, encrypted)
            if decrypted:
                override["openai_api_key"] = decrypted
        else:
            override["api_key_encrypted"] = encrypted
    return override


async def save_override(db: AsyncSession, settings: Settings, payload) -> dict:
    """Persist a model override from a validated update payload."""
    existing = await load_override(db, settings) or {}
    encrypted = existing.get("api_key_encrypted") if isinstance(existing, dict) else None
    if payload.clear_api_key:
        encrypted = None
    elif payload.api_key:
        encrypted = encrypt_secret(settings, payload.api_key)

    stored = {
        "openai_base_url": payload.base_url.strip(),
        "openai_model": payload.model.strip(),
        "openai_temperature": payload.temperature,
        "openai_timeout": payload.timeout,
        "openai_max_retries": payload.max_retries,
        "openai_thinking_enabled": payload.thinking_enabled,
    }
    if encrypted:
        stored["api_key_encrypted"] = encrypted
    await RuntimeConfigService(db).set(MODEL_CONFIG_KEY, json.dumps(stored))
    return stored


async def clear_override(db: AsyncSession) -> bool:
    """Drop the runtime override so environment defaults apply again."""
    return await RuntimeConfigService(db).delete(MODEL_CONFIG_KEY)


def resolve_settings(settings: Settings, override: dict | None) -> Settings:
    """Apply a stored override on top of the environment settings."""
    if not override:
        return settings
    updates = {key: override[key] for key in _OVERRIDE_FIELDS if key in override}
    if override.get("openai_api_key"):
        updates["openai_api_key"] = override["openai_api_key"]
    return settings.model_copy(update=updates)


def describe(settings: Settings, override: dict | None) -> dict:
    """Return the effective model configuration without exposing the secret."""
    effective = resolve_settings(settings, override)
    has_runtime_key = bool(override and override.get("api_key_encrypted"))
    if has_runtime_key:
        key_source = "runtime"
    elif settings.openai_api_key:
        key_source = "environment"
    else:
        key_source = "none"
    return {
        "base_url": effective.openai_base_url,
        "model": effective.openai_model,
        "temperature": effective.openai_temperature,
        "timeout": effective.openai_timeout,
        "max_retries": effective.openai_max_retries,
        "thinking_enabled": effective.openai_thinking_enabled,
        "api_key_configured": key_source != "none",
        "api_key_source": key_source,
        "source": "runtime" if override else "environment",
    }

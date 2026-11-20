"""Saved model API profiles and the currently active one.

Profiles let operators keep several validated provider/key/model combinations
and choose which one the whole system uses. API keys are stored encrypted and
never returned; activation writes the profile into the existing runtime model
override so the pipeline hot-swaps exactly as before.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.schemas.runtime_settings import ModelConfigUpdate, ModelProfileUpsert
from app.services.model_config_service import (
    clear_override,
    decrypt_secret,
    encrypt_secret,
    save_override,
)
from app.services.model_validation_service import validate_model_config
from app.services.runtime_config_service import RuntimeConfigService

MODEL_PROFILES_KEY = "model_profiles"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _empty_state() -> dict:
    return {"active_id": None, "profiles": []}


def _load_state(raw: str) -> dict:
    if not raw:
        return _empty_state()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("The stored model profiles are not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValidationError("The stored model profiles are not an object")
    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        profiles = []
    active_id = payload.get("active_id")
    return {
        "active_id": active_id if isinstance(active_id, str) else None,
        "profiles": [item for item in profiles if isinstance(item, dict)],
    }


async def _load(db: AsyncSession) -> dict:
    raw = await RuntimeConfigService(db).get(MODEL_PROFILES_KEY)
    return _load_state(raw)


async def _store(db: AsyncSession, state: dict) -> None:
    await RuntimeConfigService(db).set(MODEL_PROFILES_KEY, json.dumps(state))


def _public(profile: dict, active_id: str | None) -> dict:
    return {
        "id": profile["id"],
        "name": profile.get("name", ""),
        "provider": profile.get("provider", "openai"),
        "base_url": profile.get("base_url", ""),
        "model": profile.get("model", ""),
        "api_version": profile.get("api_version", ""),
        "temperature": profile.get("temperature", 1.0),
        "timeout": profile.get("timeout", 60),
        "max_retries": profile.get("max_retries", 3),
        "thinking_enabled": bool(profile.get("thinking_enabled", False)),
        "api_key_configured": bool(profile.get("api_key_encrypted")),
        "valid": bool(profile.get("valid", False)),
        "validation_message": profile.get("validation_message", ""),
        "validated_at": profile.get("validated_at"),
        "created_at": profile.get("created_at", ""),
        "updated_at": profile.get("updated_at", ""),
        "active": profile["id"] == active_id,
    }


def _find(state: dict, profile_id: str) -> dict:
    for profile in state["profiles"]:
        if profile.get("id") == profile_id:
            return profile
    raise NotFoundError("Saved API profile not found")


def _profile_fields(payload: ModelProfileUpsert) -> dict:
    return {
        "name": payload.name.strip(),
        "provider": payload.provider,
        "base_url": payload.base_url,
        "model": payload.model.strip(),
        "api_version": payload.api_version,
        "temperature": payload.temperature,
        "timeout": payload.timeout,
        "max_retries": payload.max_retries,
        "thinking_enabled": payload.thinking_enabled,
    }


async def list_profiles(db: AsyncSession) -> dict:
    """Return every saved profile without secrets, plus the active id."""
    state = await _load(db)
    return {
        "active_id": state["active_id"],
        "profiles": [_public(profile, state["active_id"]) for profile in state["profiles"]],
    }


async def save_profile(
    db: AsyncSession,
    settings,
    payload: ModelProfileUpsert,
    profile_id: str | None = None,
) -> dict:
    """Create or update a profile, validate it and persist the result."""
    state = await _load(db)
    existing = _find(state, profile_id) if profile_id else None
    encrypted = existing.get("api_key_encrypted") if existing else None
    if payload.clear_api_key:
        encrypted = None
    elif payload.api_key:
        encrypted = encrypt_secret(settings, payload.api_key)
    if not encrypted:
        raise ValidationError("An API key is required for a saved API profile")
    api_key = decrypt_secret(settings, encrypted)
    if not api_key:
        raise ValidationError("The stored API key could not be decrypted")

    now = _now()
    profile = {
        **_profile_fields(payload),
        "id": existing["id"] if existing else str(uuid.uuid4()),
        "api_key_encrypted": encrypted,
        "valid": False,
        "validation_message": "",
        "validated_at": None,
        "created_at": existing.get("created_at") if existing else now,
        "updated_at": now,
    }
    valid, message = await validate_model_config(
        provider=profile["provider"],
        base_url=profile["base_url"],
        api_version=profile["api_version"],
        api_key=api_key,
        model=profile["model"],
    )
    profile["valid"] = valid
    profile["validation_message"] = message
    profile["validated_at"] = now

    if existing is None:
        state["profiles"].append(profile)
    else:
        state["profiles"] = [
            profile if item.get("id") == profile["id"] else item for item in state["profiles"]
        ]
    await _store(db, state)
    return _public(profile, state["active_id"])


async def validate_profile(db: AsyncSession, settings, profile_id: str) -> dict:
    """Re-run validation for one saved profile."""
    state = await _load(db)
    profile = _find(state, profile_id)
    api_key = decrypt_secret(settings, profile.get("api_key_encrypted", ""))
    if not api_key:
        raise ValidationError("The stored API key could not be decrypted")
    valid, message = await validate_model_config(
        provider=profile.get("provider", "openai"),
        base_url=profile.get("base_url", ""),
        api_version=profile.get("api_version", ""),
        api_key=api_key,
        model=profile.get("model", ""),
    )
    profile["valid"] = valid
    profile["validation_message"] = message
    profile["validated_at"] = _now()
    profile["updated_at"] = profile["validated_at"]
    await _store(db, state)
    return _public(profile, state["active_id"])


async def activate_profile(db: AsyncSession, settings, profile_id: str) -> dict:
    """Make one validated profile the system-wide model configuration."""
    state = await _load(db)
    profile = _find(state, profile_id)
    if not profile.get("valid"):
        raise ValidationError("Validate this API profile before activating it")
    api_key = decrypt_secret(settings, profile.get("api_key_encrypted", ""))
    if not api_key:
        raise ValidationError("The stored API key could not be decrypted")
    update = ModelConfigUpdate(
        provider=profile.get("provider", "openai"),
        base_url=profile.get("base_url", ""),
        model=profile.get("model", ""),
        api_version=profile.get("api_version", "2024-10-21"),
        temperature=profile.get("temperature", 1.0),
        timeout=profile.get("timeout", 60),
        max_retries=profile.get("max_retries", 3),
        thinking_enabled=bool(profile.get("thinking_enabled", False)),
        api_key=api_key,
    )
    await save_override(db, settings, update)
    state["active_id"] = profile_id
    await _store(db, state)
    return _public(profile, state["active_id"])


async def deactivate_profile(db: AsyncSession) -> None:
    """Fall back to the environment model configuration."""
    state = await _load(db)
    state["active_id"] = None
    await _store(db, state)
    await clear_override(db)


async def delete_profile(db: AsyncSession, settings, profile_id: str) -> None:
    """Delete a profile; an active profile also clears the runtime override."""
    state = await _load(db)
    profile = _find(state, profile_id)
    state["profiles"] = [item for item in state["profiles"] if item.get("id") != profile["id"]]
    if state["active_id"] == profile_id:
        state["active_id"] = None
        await clear_override(db)
    await _store(db, state)

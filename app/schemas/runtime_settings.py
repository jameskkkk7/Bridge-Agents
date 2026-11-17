"""Schemas for runtime model configuration and the agent prompt."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class ModelConfigView(BaseModel):
    """Effective model configuration shown in the studio."""

    base_url: str
    model: str
    temperature: float
    timeout: int
    max_retries: int
    thinking_enabled: bool
    api_key_configured: bool
    api_key_source: Literal["runtime", "environment", "none"]
    source: Literal["runtime", "environment"]


class ModelConfigUpdate(BaseModel):
    """Validated update for the runtime model configuration."""

    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    temperature: float = Field(default=1.0, ge=0, le=2)
    timeout: int = Field(default=60, ge=1, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)
    thinking_enabled: bool = False
    api_key: str | None = Field(
        default=None,
        max_length=500,
        description="New API key; omit to keep the stored key.",
    )
    clear_api_key: bool = False

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        parsed = urlparse(cleaned)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("base_url must be an http(s) URL with a host")
        if parsed.username or parsed.password:
            raise ValueError("base_url must not contain credentials")
        return cleaned

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("model must not be empty")
        return cleaned


class AgentPromptView(BaseModel):
    """The current agent role prompt and where it comes from."""

    system_prompt: str
    source: Literal["saved_graph", "default_graph"]


class AgentPromptUpdate(BaseModel):
    """New agent role prompt."""

    system_prompt: str = Field(min_length=1, max_length=4000)

    @field_validator("system_prompt")
    @classmethod
    def _validate_prompt(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("system_prompt must not be empty")
        return cleaned

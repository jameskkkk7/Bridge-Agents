"""Schemas for runtime model configuration and the agent prompt."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

# Vendors selectable in Studio -> Settings. Everything except Azure OpenAI is
# called through its OpenAI-compatible chat-completions endpoint.
MODEL_PROVIDERS = (
    "openai",
    "azure",
    "deepseek",
    "qwen",
    "moonshot",
    "zhipu",
    "volcengine",
    "baidu",
    "minimax",
    "siliconflow",
    "openrouter",
    "gemini",
    "anthropic",
    "ollama",
    "custom",
)


class ModelConfigView(BaseModel):
    """Effective model configuration shown in the studio."""

    provider: str
    base_url: str
    model: str
    temperature: float
    timeout: int
    max_retries: int
    thinking_enabled: bool
    api_version: str = ""
    api_key_configured: bool
    api_key_source: Literal["runtime", "environment", "none"]
    source: Literal["runtime", "environment"]


class ModelConfigUpdate(BaseModel):
    """Validated update for the runtime model configuration."""

    provider: str = Field(default="openai", max_length=40)
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    temperature: float = Field(default=1.0, ge=0, le=2)
    timeout: int = Field(default=60, ge=1, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)
    thinking_enabled: bool = False
    api_version: str = Field(default="2024-10-21", max_length=40)
    api_key: str | None = Field(
        default=None,
        max_length=500,
        description="New API key; omit to keep the stored key.",
    )
    clear_api_key: bool = False

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in MODEL_PROVIDERS:
            raise ValueError(f"unsupported model provider: {cleaned}")
        return cleaned

    @field_validator("api_version")
    @classmethod
    def _validate_api_version(cls, value: str) -> str:
        return value.strip()

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


class ModelCatalogRequest(BaseModel):
    """Unsaved model settings used to ask the provider for its model list."""

    provider: str = Field(default="openai", max_length=40)
    base_url: str = Field(min_length=1, max_length=500)
    api_version: str = Field(default="2024-10-21", max_length=40)
    api_key: str | None = Field(
        default=None,
        max_length=500,
        description="Optional new key; the stored/environment key is used when omitted.",
    )

    @field_validator("provider")
    @classmethod
    def _validate_catalog_provider(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in MODEL_PROVIDERS:
            raise ValueError(f"unsupported model provider: {cleaned}")
        return cleaned

    @field_validator("base_url")
    @classmethod
    def _validate_catalog_base_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        parsed = urlparse(cleaned)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("base_url must be an http(s) URL with a host")
        if parsed.username or parsed.password:
            raise ValueError("base_url must not contain credentials")
        return cleaned

    @field_validator("api_version")
    @classmethod
    def _validate_catalog_api_version(cls, value: str) -> str:
        return value.strip()


class ModelProfileUpsert(ModelConfigUpdate):
    """Create or update a saved API profile (validated like a model update)."""

    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be empty")
        return cleaned


class ModelProfileView(BaseModel):
    """A saved API profile shown in Studio; the API key is never included."""

    id: str
    name: str
    provider: str
    base_url: str
    model: str
    api_version: str
    temperature: float
    timeout: int
    max_retries: int
    thinking_enabled: bool
    api_key_configured: bool
    valid: bool
    validation_message: str = ""
    validated_at: str | None = None
    created_at: str = ""
    updated_at: str = ""
    active: bool = False


class ModelProfileList(BaseModel):
    """All saved profiles plus the id of the active one (None = environment)."""

    active_id: str | None = None
    profiles: list[ModelProfileView] = Field(default_factory=list)


class ModelCatalogResponse(BaseModel):
    """Models discovered from the provider, never including the API key."""

    provider: str
    base_url: str
    models: list[str]
    api_key_source: Literal["request", "runtime", "environment", "none"]


class AgentPromptView(BaseModel):
    """The current agent role prompt and where it comes from."""

    system_prompt: str
    source: Literal["saved_graph", "default_graph"]


class AgentPromptUpdate(BaseModel):
    """New agent role prompt."""

    system_prompt: str = Field(min_length=1, max_length=8000)

    @field_validator("system_prompt")
    @classmethod
    def _validate_prompt(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("system_prompt must not be empty")
        return cleaned

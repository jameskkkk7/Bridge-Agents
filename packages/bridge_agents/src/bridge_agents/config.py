"""Application configuration loaded from the environment.

Every field maps to an upper-case environment variable with the same name.
Comma-separated list settings are exposed through read-only list properties so
the raw environment value stays a simple string.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the API process and helper scripts."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Bridge-Agents"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = ""
    allowed_hosts: str = "*"

    # Storage
    database_url: str = "sqlite+aiosqlite:///./data/bridge-agents.db"
    storage_dir: str = "./data/uploads"
    docs_dir: str = ""
    knowledge_dir: str = "./data/knowledge"
    default_timezone: str = "UTC"
    max_image_size: int = 10 * 1024 * 1024

    # Retrieval-augmented generation
    rag_enabled: bool = True
    rag_embedder: str = "hash"
    rag_embedding_model: str = "text-embedding-3-small"
    rag_top_k: int = 4
    rag_min_score: float = 0.12
    rag_chunk_size: int = 900
    rag_chunk_overlap: int = 120
    rag_max_context_chars: int = 2400

    # Authentication
    auth_verifier: str = "hs256"
    jwt_secret: str = "dev-only-change-me"
    jwt_issuer: str = "bridge-agents"
    jwt_audience: str = ""
    jwt_expires_minutes: int = 24 * 60
    rs256_public_key_path: str = ""
    jwks_url: str = ""
    jwks_cache_seconds: int = 300
    allow_dev_login: bool = False

    # LLM
    llm_mode: str = "mock"
    # openai | azure | deepseek | qwen | moonshot | zhipu | volcengine | baidu |
    # minimax | siliconflow | openrouter | gemini | anthropic | ollama | custom
    llm_provider: str = "openai"
    openai_api_version: str = "2024-10-21"
    openai_base_url: str = "http://mock-llm:8001/v1"
    openai_api_key: str = "not-needed"
    openai_model: str = "mock-model"
    openai_thinking_enabled: bool = False

    # Optional provider moderation for the sanitize node
    moderation_provider: str = "openai"
    moderation_base_url: str = ""
    moderation_api_key: str = ""
    moderation_model: str = "omni-moderation-latest"
    moderation_timeout: float = 5.0
    moderation_azure_endpoint: str = ""
    moderation_azure_key: str = ""
    moderation_azure_api_version: str = "2024-09-01"
    moderation_azure_severity: int = 2
    moderation_perspective_key: str = ""
    moderation_perspective_threshold: float = 0.7
    moderation_aliyun_access_key_id: str = ""
    moderation_aliyun_access_key_secret: str = ""
    moderation_aliyun_region: str = "cn-shanghai"
    moderation_aliyun_endpoint: str = ""
    moderation_aliyun_service: str = "comment_detection"
    moderation_tencent_secret_id: str = ""
    moderation_tencent_secret_key: str = ""
    moderation_tencent_region: str = "ap-guangzhou"
    moderation_tencent_endpoint: str = ""
    moderation_tencent_biz_type: str = ""
    # Optional allow-list of provider hosts; empty means "any host the URL sets".
    moderation_allowed_hosts: str = ""

    # LLM request behaviour
    openai_temperature: float = 1.0
    openai_timeout: int = 60
    openai_max_retries: int = 3

    # Agent runtime
    agent_tools_enabled: bool = False
    ws_max_connections: int = 10000
    agent_tools: str = "[]"
    agent_injection_patterns: str = ""

    # Lark channel
    lark_enabled: bool = False
    lark_app_id: str = ""
    lark_app_secret: str = ""
    lark_encrypt_key: str = ""
    lark_verification_token: str = ""
    lark_agent_open_ids: str = ""
    lark_commands: str = "/takeover,/release,/status,/help"
    lark_api_base_url: str = "https://open.feishu.cn"

    @field_validator("app_env")
    @classmethod
    def _normalize_app_env(cls, value: str) -> str:
        return value.strip().lower()

    @property
    def is_production(self) -> bool:
        """True when the deployment identifies itself as production."""
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        """Comma-separated CORS origins as a list."""
        return _split_csv(self.cors_origins)

    @property
    def allowed_host_list(self) -> list[str]:
        """Comma-separated trusted hosts as a list."""
        return _split_csv(self.allowed_hosts) or ["*"]

    @property
    def lark_agent_open_id_list(self) -> list[str]:
        """Lark open ids treated as support agents."""
        return _split_csv(self.lark_agent_open_ids)

    @property
    def moderation_allowed_host_list(self) -> list[str]:
        """Optional hosts a moderation provider URL may point at."""
        return _split_csv(self.moderation_allowed_hosts)

    @property
    def lark_command_list(self) -> list[str]:
        """Canonical commands enabled in Lark chats."""
        return _split_csv(self.lark_commands)


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()

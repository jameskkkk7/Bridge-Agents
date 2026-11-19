"""Bridge-Agents core library.

Reusable runtime pieces extracted from the server application:

* ``bridge_agents.agent`` — review-gated LangGraph runtime and graph validation;
* ``bridge_agents.auth`` — HS256 / RS256-PEM / JWKS token verification;
* ``bridge_agents.guard`` — prompt-injection guard;
* ``bridge_agents.rate_limit`` — proxy-aware client address and window limiter;
* ``bridge_agents.config`` — settings shared with the server;
* ``bridge_agents.errors`` — expected failures with HTTP status codes;
* ``bridge_agents.runtime`` — an embeddable ``AgentRuntime`` façade;
* ``bridge_agents.testing`` — deterministic fakes for tests.

The FastAPI application, persistence models and channel adapters stay in the
server package; install the library when you want the runtime, not the product.
"""

from __future__ import annotations

from bridge_agents.agent import AgentPipeline
from bridge_agents.auth import (
    HS256Verifier,
    Identity,
    JWKSVerifier,
    Role,
    RS256PemVerifier,
    TokenVerifier,
    build_verifier,
    coerce_role,
    create_token,
)
from bridge_agents.config import Settings, get_settings
from bridge_agents.errors import (
    AccessDeniedError,
    AppError,
    AuthError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from bridge_agents.guard import PromptSafetyError, is_prompt_safe, validate_prompt
from bridge_agents.rate_limit import WindowRateLimiter, get_client_ip
from bridge_agents.runtime import AgentRuntime

__version__ = "0.1.0"

__all__ = [
    "AccessDeniedError",
    "AgentPipeline",
    "AgentRuntime",
    "AppError",
    "AuthError",
    "ExternalServiceError",
    "HS256Verifier",
    "Identity",
    "JWKSVerifier",
    "NotFoundError",
    "PromptSafetyError",
    "Role",
    "RS256PemVerifier",
    "Settings",
    "TokenVerifier",
    "ValidationError",
    "WindowRateLimiter",
    "__version__",
    "build_verifier",
    "coerce_role",
    "create_token",
    "get_client_ip",
    "get_settings",
    "is_prompt_safe",
    "validate_prompt",
]

"""Token verification (re-exported from the core library)."""

from __future__ import annotations

from bridge_agents.auth import (
    HS256,
    RS256,
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

__all__ = [
    "HS256",
    "HS256Verifier",
    "Identity",
    "JWKSVerifier",
    "RS256",
    "RS256PemVerifier",
    "Role",
    "TokenVerifier",
    "build_verifier",
    "coerce_role",
    "create_token",
]

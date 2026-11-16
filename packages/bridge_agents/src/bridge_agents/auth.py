"""Token verification and local token issuance.

Three verifier back ends are available through ``AUTH_VERIFIER``:

* ``hs256`` - locally signed tokens, used by the demo and by tests;
* ``rs256_pem`` - tokens signed by a provider whose public key is a PEM file;
* ``jwks`` - tokens signed by an OIDC provider reachable through a JWKS URL.

Roles are resolved once, when a user is first seen; an unknown role claim
degrades to ``USER`` instead of failing the request.
"""

from __future__ import annotations

import asyncio
import enum
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

from bridge_agents.config import Settings
from bridge_agents.errors import AuthError
from bridge_agents.utils import utcnow


class Role(enum.StrEnum):
    """Locally assigned role: end customer, support agent, administrator."""

    USER = "USER"
    AGENT = "AGENT"
    ADMIN = "ADMIN"


HS256 = "HS256"
RS256 = "RS256"

_ROLE_ALIASES = {
    "USER": Role.USER,
    "CUSTOMER": Role.USER,
    "ROLE_USER": Role.USER,
    "AGENT": Role.AGENT,
    "SUPPORT": Role.AGENT,
    "ROLE_AGENT": Role.AGENT,
    "ADMIN": Role.ADMIN,
    "ROLE_ADMIN": Role.ADMIN,
}


def coerce_role(value: Any) -> Role:
    """Map a provider role claim onto the local three-role model."""
    if isinstance(value, Role):
        return value
    return _ROLE_ALIASES.get(str(value or "").strip().upper(), Role.USER)


@dataclass(frozen=True, slots=True)
class Identity:
    """A verified external identity before it is persisted locally."""

    id: str
    role: Role
    email: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False)


class TokenVerifier(Protocol):
    """Verifies a bearer token and returns the caller identity."""

    async def verify(self, token: str) -> Identity:
        """Return the identity encoded in the token or raise ``AuthError``."""


def _identity_from_claims(claims: dict[str, Any]) -> Identity:
    subject = claims.get("sub") or claims.get("user_id")
    if not subject:
        raise AuthError("Token is missing a subject claim")
    email = claims.get("email")
    return Identity(
        id=str(subject),
        role=coerce_role(claims.get("role")),
        email=str(email) if email else None,
        raw=claims,
    )


def _decode_options(audience: str | None) -> dict[str, Any]:
    return {"verify_aud": audience is not None}


class HS256Verifier:
    """Verifies tokens signed with the shared local secret."""

    def __init__(self, secret: str, issuer: str = "", audience: str = "") -> None:
        if not secret:
            raise ValueError("The HS256 verifier requires a non-empty secret")
        self._secret = secret
        self._issuer = issuer or None
        self._audience = audience or None

    async def verify(self, token: str) -> Identity:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[HS256],
                issuer=self._issuer,
                audience=self._audience,
                options=_decode_options(self._audience),
            )
        except jwt.PyJWTError as exc:
            raise AuthError("Invalid or expired token") from exc
        return _identity_from_claims(claims)


class RS256PemVerifier:
    """Verifies RS256 tokens against a PEM encoded public key."""

    def __init__(self, public_key_path: str, issuer: str = "", audience: str = "") -> None:
        if not public_key_path:
            raise ValueError("The RS256 verifier requires a public key path")
        self._key_path = Path(public_key_path)
        self._issuer = issuer or None
        self._audience = audience or None
        self._public_key: str | None = None

    def _load_public_key(self) -> str:
        if self._public_key is None:
            try:
                self._public_key = self._key_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise AuthError("Verification public key is unavailable") from exc
        return self._public_key

    async def verify(self, token: str) -> Identity:
        try:
            claims = jwt.decode(
                token,
                self._load_public_key(),
                algorithms=[RS256],
                issuer=self._issuer,
                audience=self._audience,
                options=_decode_options(self._audience),
            )
        except jwt.PyJWTError as exc:
            raise AuthError("Invalid or expired token") from exc
        return _identity_from_claims(claims)


class JWKSVerifier:
    """Verifies RS256 tokens using signing keys published by an OIDC issuer."""

    def __init__(
        self,
        jwks_url: str,
        issuer: str = "",
        audience: str = "",
        cache_seconds: int = 300,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not jwks_url:
            raise ValueError("The JWKS verifier requires a JWKS URL")
        self._url = jwks_url
        self._issuer = issuer or None
        self._audience = audience or None
        self._cache_seconds = max(1, cache_seconds)
        self._transport = transport
        self._clock = clock
        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def _fetch_keys(self) -> None:
        async with httpx.AsyncClient(transport=self._transport, timeout=10.0) as client:
            try:
                response = await client.get(self._url)
                response.raise_for_status()
                document = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise AuthError("Could not load the JWKS document") from exc
        keys: dict[str, Any] = {}
        for item in document.get("keys", []):
            key_id = item.get("kid")
            if not key_id:
                continue
            try:
                keys[key_id] = RSAAlgorithm.from_jwk(json.dumps(item))
            except (jwt.PyJWTError, ValueError):
                continue
        self._keys = keys
        self._fetched_at = self._clock()

    def _is_stale(self) -> bool:
        return self._clock() - self._fetched_at >= self._cache_seconds

    async def _signing_key(self, key_id: str | None) -> Any:
        if self._is_stale() or key_id not in self._keys:
            async with self._lock:
                if self._is_stale() or key_id not in self._keys:
                    await self._fetch_keys()
        if key_id is not None:
            key = self._keys.get(key_id)
        elif len(self._keys) == 1:
            key = next(iter(self._keys.values()))
        else:
            key = None
        if key is None:
            raise AuthError("Unknown token signing key")
        return key

    async def verify(self, token: str) -> Identity:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthError("Invalid or expired token") from exc
        key = await self._signing_key(header.get("kid"))
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[RS256],
                issuer=self._issuer,
                audience=self._audience,
                options=_decode_options(self._audience),
            )
        except jwt.PyJWTError as exc:
            raise AuthError("Invalid or expired token") from exc
        return _identity_from_claims(claims)


def build_verifier(settings: Settings) -> TokenVerifier:
    """Create the verifier selected by ``AUTH_VERIFIER``."""
    kind = settings.auth_verifier.strip().lower()
    if kind == "hs256":
        return HS256Verifier(settings.jwt_secret, settings.jwt_issuer, settings.jwt_audience)
    if kind == "rs256_pem":
        return RS256PemVerifier(
            settings.rs256_public_key_path, settings.jwt_issuer, settings.jwt_audience
        )
    if kind == "jwks":
        return JWKSVerifier(
            settings.jwks_url,
            settings.jwt_issuer,
            settings.jwt_audience,
            settings.jwks_cache_seconds,
        )
    raise ValueError(f"Unsupported AUTH_VERIFIER value: {settings.auth_verifier!r}")


def create_token(settings: Settings, subject: str, role: Role) -> str:
    """Issue a short-lived HS256 token for local use and demos."""
    issued_at = utcnow()
    claims: dict[str, Any] = {
        "sub": subject,
        "role": role.value,
        "iss": settings.jwt_issuer,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=settings.jwt_expires_minutes),
    }
    if settings.jwt_audience:
        claims["aud"] = settings.jwt_audience
    return jwt.encode(claims, settings.jwt_secret, algorithm=HS256)

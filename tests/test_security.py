"""Unit tests for the token verifiers."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.config import Settings
from app.core.exceptions import AuthError
from app.core.security import (
    HS256Verifier,
    JWKSVerifier,
    Role,
    RS256PemVerifier,
    build_verifier,
    coerce_role,
)

SECRET = "test-secret-key-for-pytest-only-32b"
ISSUER = "bridge-agents-test"


def _claims(**overrides: object) -> dict[str, object]:
    claims: dict[str, object] = {"sub": "user-1", "role": "AGENT", "iss": ISSUER}
    claims.update(overrides)
    return claims


def _rsa_key_pair() -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def _jwks_document(public_pem: bytes, key_id: str) -> dict[str, object]:
    public_key = serialization.load_pem_public_key(public_pem)
    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk.update({"kid": key_id, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


async def test_hs256_verifier_accepts_valid_token() -> None:
    verifier = HS256Verifier(SECRET, ISSUER)
    token = jwt.encode(_claims(), SECRET, algorithm="HS256")
    identity = await verifier.verify(token)
    assert identity.id == "user-1"
    assert identity.role is Role.AGENT


async def test_hs256_verifier_rejects_wrong_signature() -> None:
    verifier = HS256Verifier(SECRET, ISSUER)
    token = jwt.encode(_claims(), "another-secret-key-that-is-32-bytes!", algorithm="HS256")
    with pytest.raises(AuthError):
        await verifier.verify(token)


async def test_hs256_verifier_rejects_wrong_issuer() -> None:
    verifier = HS256Verifier(SECRET, ISSUER)
    token = jwt.encode(_claims(iss="somebody-else"), SECRET, algorithm="HS256")
    with pytest.raises(AuthError):
        await verifier.verify(token)


async def test_hs256_verifier_rejects_expired_token() -> None:
    verifier = HS256Verifier(SECRET, ISSUER)
    token = jwt.encode(_claims(exp=1), SECRET, algorithm="HS256")
    with pytest.raises(AuthError):
        await verifier.verify(token)


async def test_verifier_requires_a_subject_claim() -> None:
    verifier = HS256Verifier(SECRET, ISSUER)
    token = jwt.encode({"role": "AGENT", "iss": ISSUER}, SECRET, algorithm="HS256")
    with pytest.raises(AuthError):
        await verifier.verify(token)


def test_unknown_roles_degrade_to_user() -> None:
    assert coerce_role("superuser") is Role.USER
    assert coerce_role(None) is Role.USER
    assert coerce_role("ROLE_ADMIN") is Role.ADMIN
    assert coerce_role("agent") is Role.AGENT


async def test_rs256_pem_verifier_accepts_valid_token(tmp_path: Path) -> None:
    private_pem, public_pem = _rsa_key_pair()
    key_file = tmp_path / "provider-public.pem"
    key_file.write_bytes(public_pem)
    verifier = RS256PemVerifier(str(key_file), ISSUER)
    token = jwt.encode(_claims(), private_pem, algorithm="RS256")
    identity = await verifier.verify(token)
    assert identity.id == "user-1"
    assert identity.role is Role.AGENT


async def test_rs256_pem_verifier_reports_missing_key(tmp_path: Path) -> None:
    verifier = RS256PemVerifier(str(tmp_path / "absent.pem"), ISSUER)
    token = jwt.encode(_claims(), "not-a-key-but-32-bytes-long-for-hs256!", algorithm="HS256")
    with pytest.raises(AuthError):
        await verifier.verify(token)


async def test_jwks_verifier_fetches_then_caches_keys() -> None:
    private_pem, public_pem = _rsa_key_pair()
    document = _jwks_document(public_pem, "key-1")
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json=document)

    verifier = JWKSVerifier(
        "https://issuer.test/.well-known/jwks.json",
        ISSUER,
        transport=httpx.MockTransport(handler),
    )
    token = jwt.encode(_claims(), private_pem, algorithm="RS256", headers={"kid": "key-1"})
    assert (await verifier.verify(token)).id == "user-1"
    assert (await verifier.verify(token)).id == "user-1"
    assert calls["count"] == 1


async def test_jwks_verifier_refreshes_for_an_unknown_key() -> None:
    private_pem, public_pem = _rsa_key_pair()
    document = _jwks_document(public_pem, "key-1")
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json=document)

    verifier = JWKSVerifier(
        "https://issuer.test/.well-known/jwks.json",
        ISSUER,
        transport=httpx.MockTransport(handler),
    )
    token = jwt.encode(_claims(), private_pem, algorithm="RS256", headers={"kid": "unknown"})
    with pytest.raises(AuthError):
        await verifier.verify(token)
    assert calls["count"] == 1


def test_build_verifier_selects_the_configured_backend() -> None:
    hs256_settings = Settings(auth_verifier="hs256", jwt_secret=SECRET, jwt_issuer=ISSUER)
    assert isinstance(build_verifier(hs256_settings), HS256Verifier)

    pem_settings = Settings(auth_verifier="rs256_pem", rs256_public_key_path="provider-public.pem")
    assert isinstance(build_verifier(pem_settings), RS256PemVerifier)

    jwks_settings = Settings(auth_verifier="jwks", jwks_url="https://issuer.test/jwks")
    assert isinstance(build_verifier(jwks_settings), JWKSVerifier)

    with pytest.raises(ValueError):
        build_verifier(Settings(auth_verifier="magic"))

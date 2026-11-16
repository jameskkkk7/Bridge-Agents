"""Request and response schemas for authentication."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TokenVerifyRequest(BaseModel):
    """A token issued by the configured identity provider."""

    token: str = Field(min_length=1, description="Bearer token to verify")


class UserResponse(BaseModel):
    """Public description of a user account."""

    id: str
    role: str
    email: str | None = None


class MeResponse(UserResponse):
    """Identity of the caller behind the current token."""


class AuthResponse(BaseModel):
    """Token plus identity returned by the login and verify endpoints."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse

"""Authentication endpoints: token verification, identity and demo login."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import create_token
from app.models.database import get_db
from app.models.user import Role, User
from app.schemas.auth import AuthResponse, MeResponse, TokenVerifyRequest, UserResponse
from app.services.user_service import UserService

router = APIRouter()
dev_router = APIRouter()


def _public_user(user: User) -> UserResponse:
    return UserResponse(id=user.id, role=user.role.value, email=user.email)


@router.post("/verify", response_model=AuthResponse)
async def verify_external_token(
    data: TokenVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Validate a provider-issued token and return the local identity.

    The token itself is echoed back: it stays the credential for later calls
    and is verified again by whichever verifier is configured.
    """
    identity = await request.app.state.token_verifier.verify(data.token)
    user = await UserService(db).get_or_create_from_identity(identity)
    return AuthResponse(access_token=data.token, token_type="bearer", user=_public_user(user))


@router.get("/me", response_model=MeResponse)
async def read_current_user(user: User = Depends(get_current_user)) -> MeResponse:
    """Return the identity behind the current bearer token."""
    return MeResponse(id=user.id, role=user.role.value, email=user.email)


@dev_router.post("/dev-login", response_model=AuthResponse)
async def dev_login(
    request: Request,
    role: Literal["user", "agent", "admin"] = Query(default="user"),
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Issue a local token for one of the stable demo accounts.

    Mounted only when ``ALLOW_DEV_LOGIN=true`` and the environment is not
    production. Each role has its own account, so no stored role is rewritten.
    """
    settings = request.app.state.settings
    user = await UserService(db).get_or_create_dev_user(Role(role.upper()))
    token = create_token(settings, subject=user.id, role=user.role)
    return AuthResponse(access_token=token, token_type="bearer", user=_public_user(user))

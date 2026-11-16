"""Reusable FastAPI dependencies for authentication and authorisation."""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AccessDeniedError, AuthError
from app.models.database import get_db
from app.models.user import Role, User
from app.services.user_service import UserService

bearer_scheme = HTTPBearer(auto_error=False)

_STAFF_ROLES = frozenset({Role.AGENT, Role.ADMIN})


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the caller from the ``Authorization: Bearer`` token.

    The first time a verified identity is seen, a local account is created.
    """
    if credentials is None or not credentials.credentials:
        raise AuthError("Authentication required")

    verifier = request.app.state.token_verifier
    identity = await verifier.verify(credentials.credentials)
    user = await UserService(db).get_or_create_from_identity(identity)
    if not user.is_active:
        raise AuthError("This account is inactive")
    return user


async def require_user(user: User = Depends(get_current_user)) -> User:
    """Any authenticated role may use customer-facing endpoints."""
    return user


async def require_agent(user: User = Depends(get_current_user)) -> User:
    """Support agents and administrators may access staff endpoints."""
    if user.role not in _STAFF_ROLES:
        raise AccessDeniedError("Support staff access required")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Only administrators may manage the user directory."""
    if user.role is not Role.ADMIN:
        raise AccessDeniedError("Administrator access required")
    return user


def ensure_session_access(user: User, session_user_id: str) -> None:
    """Raise unless the caller owns the session or is support staff."""
    if user.role in _STAFF_ROLES:
        return
    if user.id != session_user_id:
        raise AccessDeniedError("Access denied to this session")

"""Admin API router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.admin import knowledge, runtime_config, sessions, users

router = APIRouter(redirect_slashes=False)
router.include_router(
    runtime_config.router, prefix="/runtime-config", tags=["admin-runtime-config"]
)
router.include_router(knowledge.router, prefix="/knowledge", tags=["admin-knowledge"])
router.include_router(sessions.router, prefix="/sessions", tags=["admin-sessions"])
router.include_router(users.router, prefix="/users", tags=["admin-users"])

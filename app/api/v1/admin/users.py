"""Admin user directory (read-only in v0.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.models.database import get_db
from app.models.user import User
from app.schemas.admin import AdminUserItem, AdminUserList
from app.services.session_service import clamp_page

router = APIRouter()


@router.get("", response_model=AdminUserList)
async def list_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserList:
    """List user accounts; only administrators may access the directory."""
    page, limit = clamp_page(page, limit)
    total = int((await db.execute(select(func.count()).select_from(User))).scalar() or 0)
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset((page - 1) * limit).limit(limit)
    )
    users = list(result.scalars().all())
    return AdminUserList(
        items=[
            AdminUserItem(
                id=user.id,
                email=user.email,
                role=user.role.value,
                is_active=user.is_active,
                created_at=user.created_at,
            )
            for user in users
        ],
        total=total,
        page=page,
        limit=limit,
    )

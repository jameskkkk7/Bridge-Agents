"""Persistence helpers for user accounts."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Identity
from app.models.user import Role, User


class UserService:
    """Create and look up local accounts for verified identities."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, user_id: str) -> User | None:
        """Return the account with the given id."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Return the account with the given e-mail address."""
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_or_create_from_identity(self, identity: Identity) -> User:
        """Return the stored account, creating it the first time it is seen.

        The role is written once at creation time. Later token claims do not
        rewrite stored roles: a provider change must be applied by an explicit
        administrative action instead of silently following the token.
        """
        existing = await self.get(identity.id)
        if existing is not None:
            return existing
        user = User(id=identity.id, email=identity.email, role=identity.role)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get_or_create_dev_user(
        self,
        role: Role,
        *,
        client_id: str | None = None,
        display_name: str | None = None,
    ) -> User:
        """Return a stable demo account for one role.

        Customers pass a browser-scoped ``client_id`` plus the nickname they
        entered, so each demo visitor gets a separate account (their own
        conversation list) while support staff keep using the shared role
        accounts. Switching roles never mutates a stored role.
        """
        if role is Role.USER and client_id:
            email = f"demo-{client_id}@bridge-agents.local"
            existing = await self.get_by_email(email)
            if existing is not None:
                if display_name and existing.display_name != display_name:
                    existing.display_name = display_name
                    await self.db.commit()
                    await self.db.refresh(existing)
                return existing
            user = User(email=email, role=role, display_name=display_name)
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
            return user

        email = f"dev-{role.value.lower()}@bridge-agents.local"
        existing = await self.get_by_email(email)
        if existing is not None:
            return existing
        user = User(email=email, role=role)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

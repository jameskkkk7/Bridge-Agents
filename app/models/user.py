"""User account model and the local role enumeration."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from bridge_agents.auth import Role
from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.session import Session


def _role_values(enum_class: type[enum.Enum]) -> list[str]:
    return [str(member.value) for member in enum_class]


class User(BaseModel):
    """An authenticated end customer or staff member."""

    __tablename__ = "users"

    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=16, values_callable=_role_values),
        default=Role.USER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    sessions: Mapped[list[Session]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

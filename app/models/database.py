"""Async database engine, session factory and schema bootstrap."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.models.base import Base


def _prepare_sqlite_directory(database_url: URL) -> None:
    """Create the parent directory for file-backed SQLite databases."""
    if database_url.get_backend_name() != "sqlite":
        return
    database = database_url.database
    if not database or database == ":memory:":
        return
    Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def build_engine(database_url: str) -> AsyncEngine:
    """Build an async engine; SQLite files use a connection pool of one shot."""
    url = make_url(database_url)
    _prepare_sqlite_directory(url)
    if url.get_backend_name() == "sqlite":
        return create_async_engine(database_url, echo=False, poolclass=NullPool)
    return create_async_engine(database_url, echo=False)


settings = get_settings()
engine: AsyncEngine = build_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    """Create every table declared on the shared metadata."""
    import app.models  # noqa: F401  (registers models on Base.metadata)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        # SQLAlchemy create_all does not add columns to existing tables; keep
        # local demo databases working across upgrades.
        table_names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
        if "users" in table_names:
            columns = await connection.run_sync(
                lambda sync: {column["name"] for column in inspect(sync).get_columns("users")}
            )
            if "display_name" not in columns:
                await connection.execute(
                    text("ALTER TABLE users ADD COLUMN display_name VARCHAR(80)")
                )


async def dispose_engine() -> None:
    """Close all pooled connections (used at shutdown and in tests)."""
    await engine.dispose()


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a database session."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

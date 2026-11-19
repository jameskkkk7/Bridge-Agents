"""Shared pytest fixtures: isolated settings, schema and HTTP client."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

TMP_DIR = Path(tempfile.mkdtemp(prefix="bridge-agents-tests-"))
REPO_ROOT = Path(__file__).resolve().parents[1]

os.environ.update(
    {
        "APP_ENV": "test",
        "DEBUG": "false",
        "LOG_LEVEL": "WARNING",
        "DATABASE_URL": f"sqlite+aiosqlite:///{(TMP_DIR / 'test.db').as_posix()}",
        "STORAGE_DIR": str(TMP_DIR / "uploads"),
        "DOCS_DIR": str(REPO_ROOT / "docs" / "kb"),
        "KNOWLEDGE_DIR": str(TMP_DIR / "knowledge"),
        "WEB_DIST_DIR": str(TMP_DIR / "web-dist-absent"),
        "RAG_EMBEDDER": "hash",
        "ALLOWED_HOSTS": "*",
        "AUTH_VERIFIER": "hs256",
        "JWT_SECRET": "test-secret-key-for-pytest-only-32b",
        "JWT_ISSUER": "bridge-agents-test",
        "JWT_AUDIENCE": "",
        "ALLOW_DEV_LOGIN": "true",
        "LLM_MODE": "mock",
        "OPENAI_API_KEY": "not-needed",
        # Keep the suite independent from a developer's local .env file.
        "AGENT_TOOLS_ENABLED": "false",
    }
)

from app.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.database import (  # noqa: E402
    SessionLocal,
    dispose_engine,
    engine,
    init_db,
)

get_settings.cache_clear()

TEST_SECRET = "test-secret-key-for-pytest-only-32b"
TEST_ISSUER = "bridge-agents-test"


@pytest.fixture(autouse=True)
async def _database() -> AsyncIterator[None]:
    """Create the schema before each test and drop it afterwards."""
    await init_db()
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await dispose_engine()


@pytest.fixture(autouse=True)
def _knowledge() -> Iterator[None]:
    """Give every test a freshly seeded, isolated knowledge base."""
    from bridge_agents.rag.knowledge import reset_knowledge

    reset_knowledge()
    yield
    reset_knowledge()


@pytest.fixture
def app():
    """A fresh application built from the test environment."""
    return create_app()


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    """HTTP client speaking to the application in-process."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.fixture
async def db_session() -> AsyncIterator:
    """A direct database session for model level tests."""
    async with SessionLocal() as session:
        yield session

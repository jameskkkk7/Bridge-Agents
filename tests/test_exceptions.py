"""Error handling behaviour."""

from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import AccessDeniedError, NotFoundError, setup_exception_handlers


def _build_app() -> FastAPI:
    app = FastAPI()
    setup_exception_handlers(app)

    @app.get("/missing")
    async def missing() -> dict[str, str]:
        raise NotFoundError("Session not found")

    @app.get("/forbidden")
    async def forbidden() -> dict[str, str]:
        raise AccessDeniedError("Not allowed")

    return app


async def test_known_errors_render_a_json_envelope() -> None:
    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        missing = await client.get("/missing")
        forbidden = await client.get("/forbidden")

    assert missing.status_code == 404
    assert missing.json() == {"error": "NotFoundError", "message": "Session not found"}
    assert forbidden.status_code == 403
    assert forbidden.json() == {"error": "AccessDeniedError", "message": "Not allowed"}


async def test_unexpected_errors_return_a_500_envelope() -> None:
    app = _build_app()

    @app.get("/boom")
    async def boom() -> dict[str, str]:
        raise RuntimeError("kaboom")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert response.json()["error"] == "InternalError"

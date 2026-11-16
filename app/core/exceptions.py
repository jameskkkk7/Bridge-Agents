"""Expected application failures and their HTTP representation."""

from __future__ import annotations

from bridge_agents.errors import (
    AccessDeniedError,
    AppError,
    AuthError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

__all__ = [
    "AccessDeniedError",
    "AppError",
    "AuthError",
    "ExternalServiceError",
    "NotFoundError",
    "ValidationError",
    "setup_exception_handlers",
]


def setup_exception_handlers(app: FastAPI) -> None:
    """Register JSON error handlers on the given application."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error_name, "message": exc.message},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": "InternalError", "message": "An unexpected error occurred"},
        )

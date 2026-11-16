"""Application factory and HTTP entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1 import auth, channels, images, messages, sessions
from app.api.v1.admin import router as admin_router
from app.config import Settings, get_settings
from app.core.agent.factory import initialize_pipeline
from app.core.exceptions import setup_exception_handlers
from app.core.logging_config import setup_logging
from app.core.security import build_verifier
from app.models.database import dispose_engine, init_db
from app.ws import gateway as realtime


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API application.

    Settings and the token verifier are attached to ``app.state`` so routers
    and tests can use one isolated application instance per configuration.
    """
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        setup_logging(config)
        await init_db()
        await initialize_pipeline(application)
        yield
        from app.services.reply_engine import cancel_all_replies

        cancel_all_replies()
        pipeline = getattr(application.state, "agent_pipeline", None)
        if pipeline is not None:
            await pipeline.close()
        await dispose_engine()

    application = FastAPI(
        title=config.app_name,
        version=config.app_version,
        description="Self-hosted agent runtime for customer conversations.",
        lifespan=lifespan,
        docs_url="/docs" if config.debug else None,
        redoc_url="/redoc" if config.debug else None,
    )
    application.state.settings = config
    application.state.token_verifier = build_verifier(config)

    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=config.allowed_host_list,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origin_list,
        allow_credentials=bool(config.cors_origin_list),
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        max_age=600,
    )
    setup_exception_handlers(application)

    application.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    if config.allow_dev_login and not config.is_production:
        application.include_router(auth.dev_router, prefix="/api/v1/auth", tags=["auth"])
    application.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
    application.include_router(sessions.router, prefix="/api/v1/sessions", tags=["sessions"])
    application.include_router(messages.router, prefix="/api/v1/sessions", tags=["messages"])
    application.include_router(images.router, prefix="/api/v1/sessions", tags=["images"])
    application.include_router(channels.router, prefix="/webhook", tags=["channels"])
    application.include_router(realtime.router, tags=["realtime"])

    @application.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": config.app_version}

    @application.get("/", tags=["ops"])
    async def root() -> dict[str, str | None]:
        return {
            "name": config.app_name,
            "version": config.app_version,
            "docs": "/docs" if config.debug else None,
        }

    return application


app = create_app()

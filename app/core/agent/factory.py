"""Application wiring for the agent pipeline.

The reusable construction and validation helpers live in the core library.
This module adds the server behaviour: loading the saved graph from the
database and hot-swapping the pipeline on the FastAPI application.
"""

from __future__ import annotations

import logging
from typing import Any

from bridge_agents.agent.factory import (
    build_chat_model,
    create_pipeline,
    default_graph_config,
    validate_graph_config,
)
from bridge_agents.agent.pipeline import LangGraphPipeline

LOGGER = logging.getLogger(__name__)

__all__ = [
    "build_chat_model",
    "create_pipeline",
    "default_graph_config",
    "ensure_pipeline",
    "initialize_pipeline",
    "reinitialize_pipeline",
    "validate_graph_config",
]


async def initialize_pipeline(application: Any) -> None:
    """Build the pipeline from the persisted graph and model configuration."""
    from app.models.database import SessionLocal
    from app.services.model_config_service import load_override, resolve_settings
    from app.services.runtime_config_service import RuntimeConfigService

    base_settings = application.state.settings
    async with SessionLocal() as session:
        graph_config = await RuntimeConfigService(session).get_agent_graph_config()
        override = await load_override(session, base_settings, include_secret=True)
    application.state.model_override = override
    application.state.agent_pipeline = create_pipeline(
        graph_config, settings=resolve_settings(base_settings, override)
    )
    LOGGER.info("agent pipeline initialised from runtime configuration")


async def reinitialize_pipeline(application: Any) -> None:
    """Rebuild the pipeline after the saved graph configuration changed."""
    previous = getattr(application.state, "agent_pipeline", None)
    await initialize_pipeline(application)
    if previous is not None:
        await previous.close()
    LOGGER.info("agent pipeline reinitialised")


async def ensure_pipeline(application: Any) -> LangGraphPipeline:
    """Return the active pipeline, creating it on first use if needed."""
    pipeline = getattr(application.state, "agent_pipeline", None)
    if pipeline is None:
        await initialize_pipeline(application)
        pipeline = application.state.agent_pipeline
    return pipeline

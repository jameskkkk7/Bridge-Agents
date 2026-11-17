"""Read and update the agent role prompt stored in the graph configuration.

The prompt is not a separate setting: it lives in the graph's ``system`` node,
which keeps one source of truth for the flow and the Studio prompt editor.
"""

from __future__ import annotations

import copy

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.factory import (
    ensure_pipeline,
    reinitialize_pipeline,
    validate_graph_config,
)
from app.core.exceptions import ValidationError
from app.services.runtime_config_service import RuntimeConfigService


async def current_graph(db: AsyncSession, application: FastAPI) -> tuple[dict, bool]:
    """Return the active graph and whether it is persisted (vs built-in)."""
    saved = await RuntimeConfigService(db).get_agent_graph_config()
    if saved is not None:
        return copy.deepcopy(saved), True
    pipeline = await ensure_pipeline(application)
    return copy.deepcopy(pipeline.get_graph_config()), False


def extract_prompt(graph: dict) -> str:
    """Return the first non-empty system prompt in the graph."""
    for node in graph.get("nodes", []):
        if node.get("type") != "system":
            continue
        prompt = (node.get("config") or {}).get("system_prompt") or ""
        if prompt.strip():
            return prompt.strip()
    return ""


async def update_prompt(db: AsyncSession, application: FastAPI, prompt: str) -> str:
    """Replace the prompt on every system node and activate the graph."""
    graph, _ = await current_graph(db, application)
    system_nodes = [node for node in graph.get("nodes", []) if node.get("type") == "system"]
    if not system_nodes:
        raise ValidationError("The graph needs a 'system' node before it can hold a prompt")
    for node in system_nodes:
        config = node.setdefault("config", {})
        config["system_prompt"] = prompt
    error = validate_graph_config(graph)
    if error is not None:
        raise ValidationError(error)
    await RuntimeConfigService(db).set_agent_graph_config(graph)
    await reinitialize_pipeline(application)
    return prompt

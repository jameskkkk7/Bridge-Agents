"""Admin endpoints for the editable agent graph."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_agent
from app.core.agent.factory import ensure_pipeline, reinitialize_pipeline, validate_graph_config
from app.core.agent.tools import get_tools
from app.core.exceptions import ValidationError
from app.models.database import get_db
from app.models.user import User
from app.schemas.runtime_config import (
    AgentGraphConfig,
    AgentGraphDiagram,
    AgentToolInfo,
    GraphConfigSaved,
)
from app.services.runtime_config_service import RuntimeConfigService

router = APIRouter()


@router.get("/agent-tools", response_model=list[AgentToolInfo])
async def list_agent_tools(_: User = Depends(require_agent)) -> list[AgentToolInfo]:
    """Return the tools that a graph node can bind."""
    return [
        AgentToolInfo(
            name=getattr(tool, "name", ""),
            description=getattr(tool, "description", "") or "",
        )
        for tool in get_tools()
    ]


@router.get("/agent-graph", response_model=AgentGraphDiagram)
async def read_agent_graph(request: Request, _: User = Depends(require_agent)) -> AgentGraphDiagram:
    """Return the current graph rendered as Mermaid source."""
    pipeline = await ensure_pipeline(request.app)
    return AgentGraphDiagram(type="mermaid", diagram=pipeline.get_mermaid_diagram())


@router.get("/agent-graph-config", response_model=AgentGraphConfig)
async def read_agent_graph_config(
    request: Request,
    _: User = Depends(require_agent),
    db: AsyncSession = Depends(get_db),
) -> AgentGraphConfig:
    """Return the editable graph, falling back to the built-in default."""
    config = await RuntimeConfigService(db).get_agent_graph_config()
    if config is None:
        pipeline = await ensure_pipeline(request.app)
        config = pipeline.get_graph_config()
    return AgentGraphConfig.model_validate(config)


@router.put("/agent-graph-config", response_model=GraphConfigSaved)
async def save_agent_graph_config(
    payload: AgentGraphConfig,
    request: Request,
    _: User = Depends(require_agent),
    db: AsyncSession = Depends(get_db),
) -> GraphConfigSaved:
    """Compile, persist and activate a graph configuration.

    The graph is compiled before it is stored: a configuration that cannot be
    built is rejected with a validation error and the saved graph stays as it
    was.
    """
    config = payload.model_dump()
    error = validate_graph_config(config)
    if error is not None:
        raise ValidationError(error)
    await RuntimeConfigService(db).set_agent_graph_config(config)
    await reinitialize_pipeline(request.app)
    return GraphConfigSaved(saved=True)


@router.delete("/agent-graph-config", response_model=GraphConfigSaved)
async def reset_agent_graph_config(
    request: Request,
    _: User = Depends(require_agent),
    db: AsyncSession = Depends(get_db),
) -> GraphConfigSaved:
    """Drop the saved configuration and activate the built-in graph again."""
    deleted = await RuntimeConfigService(db).delete_agent_graph_config()
    await reinitialize_pipeline(request.app)
    return GraphConfigSaved(saved=False, deleted=deleted)

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
from app.schemas.runtime_settings import (
    AgentPromptUpdate,
    AgentPromptView,
    ModelCatalogRequest,
    ModelCatalogResponse,
    ModelConfigUpdate,
    ModelConfigView,
)
from app.services.agent_prompt_service import (
    current_graph,
    extract_prompt,
    update_prompt,
)
from app.services.model_catalog_service import discover_models
from app.services.model_config_service import (
    clear_override,
    describe,
    load_override,
    resolve_settings,
    save_override,
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
    base_settings = request.app.state.settings
    override = await load_override(db, base_settings, include_secret=True)
    error = validate_graph_config(config, settings=resolve_settings(base_settings, override))
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


@router.get("/model-config", response_model=ModelConfigView)
async def read_model_config(
    request: Request,
    _: User = Depends(require_agent),
    db: AsyncSession = Depends(get_db),
) -> ModelConfigView:
    """Return the effective model configuration (never the API key)."""
    settings = request.app.state.settings
    override = await load_override(db, settings)
    return ModelConfigView(**describe(settings, override))


@router.post("/model-config/models", response_model=ModelCatalogResponse)
async def list_model_catalog(
    payload: ModelCatalogRequest,
    request: Request,
    _: User = Depends(require_agent),
    db: AsyncSession = Depends(get_db),
) -> ModelCatalogResponse:
    """Ask the provider for its available models (never returns the API key)."""
    settings = request.app.state.settings
    override = await load_override(db, settings, include_secret=True)
    provided_key = (payload.api_key or "").strip()
    if provided_key:
        api_key, key_source = provided_key, "request"
    elif override and override.get("openai_api_key"):
        api_key, key_source = str(override["openai_api_key"]), "runtime"
    elif settings.openai_api_key:
        api_key, key_source = settings.openai_api_key, "environment"
    else:
        api_key, key_source = None, "none"
    models = await discover_models(
        provider=payload.provider,
        base_url=payload.base_url,
        api_version=payload.api_version,
        api_key=api_key,
    )
    return ModelCatalogResponse(
        provider=payload.provider,
        base_url=payload.base_url,
        models=models,
        api_key_source=key_source,
    )


@router.put("/model-config", response_model=ModelConfigView)
async def save_model_config(
    payload: ModelConfigUpdate,
    request: Request,
    _: User = Depends(require_agent),
    db: AsyncSession = Depends(get_db),
) -> ModelConfigView:
    """Persist a model override and hot-swap the running pipeline."""
    settings = request.app.state.settings
    await save_override(db, settings, payload)
    await reinitialize_pipeline(request.app)
    override = await load_override(db, settings)
    return ModelConfigView(**describe(settings, override))


@router.delete("/model-config", response_model=ModelConfigView)
async def reset_model_config(
    request: Request,
    _: User = Depends(require_agent),
    db: AsyncSession = Depends(get_db),
) -> ModelConfigView:
    """Drop the override and fall back to environment settings."""
    settings = request.app.state.settings
    await clear_override(db)
    await reinitialize_pipeline(request.app)
    return ModelConfigView(**describe(settings, None))


@router.get("/agent-prompt", response_model=AgentPromptView)
async def read_agent_prompt(
    request: Request,
    _: User = Depends(require_agent),
    db: AsyncSession = Depends(get_db),
) -> AgentPromptView:
    """Return the agent role prompt and its source."""
    graph, saved = await current_graph(db, request.app)
    return AgentPromptView(
        system_prompt=extract_prompt(graph),
        source="saved_graph" if saved else "default_graph",
    )


@router.put("/agent-prompt", response_model=AgentPromptView)
async def save_agent_prompt(
    payload: AgentPromptUpdate,
    request: Request,
    _: User = Depends(require_agent),
    db: AsyncSession = Depends(get_db),
) -> AgentPromptView:
    """Replace the role prompt, persist and activate the graph."""
    prompt = await update_prompt(db, request.app, payload.system_prompt)
    return AgentPromptView(system_prompt=prompt, source="saved_graph")

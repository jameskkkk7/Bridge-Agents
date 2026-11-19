"""Construction and validation of the agent pipeline.

The library only needs the pure parts: build the model, produce the default
graph, validate a graph and create a pipeline. Application wiring (loading the
saved graph from a database and assigning it to an app) lives in the server.
"""

from __future__ import annotations

from typing import Any

from bridge_agents.agent.pipeline import LangGraphPipeline
from bridge_agents.agent.prompts import DEFAULT_FALLBACK_MESSAGE, DEFAULT_SYSTEM_PROMPT
from bridge_agents.config import Settings, get_settings
from bridge_agents.moderation import (
    canonical_provider,
    parse_bool_setting,
    provider_credentials_error,
    resolve_provider_base_url,
    validate_sanitize_provider_config,
)

AZURE_PROVIDERS = frozenset({"azure", "azure-openai", "azure_openai"})


def build_chat_model(settings: Settings) -> Any:
    """Create the chat model for the configured provider.

    Azure OpenAI uses the native Azure client (deployment + api-version); every
    other provider (OpenAI, DeepSeek, Qwen, Kimi, GLM, Doubao, Wenxin, MiniMax,
    Gemini, SiliconFlow, OpenRouter, Ollama, compatible gateways, ...) speaks the
    OpenAI chat-completions protocol, so one client covers them all.
    """
    from langchain_openai import AzureChatOpenAI, ChatOpenAI

    provider = (settings.llm_provider or "openai").strip().lower()
    if provider in AZURE_PROVIDERS:
        return AzureChatOpenAI(
            azure_endpoint=settings.openai_base_url,
            api_key=settings.openai_api_key,
            azure_deployment=settings.openai_model,
            api_version=settings.openai_api_version or "2024-10-21",
            temperature=settings.openai_temperature,
            timeout=settings.openai_timeout,
            max_retries=settings.openai_max_retries,
        )
    options: dict[str, Any] = {}
    if not settings.openai_thinking_enabled:
        options["extra_body"] = {"thinking": {"type": "disabled"}}
    return ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        temperature=settings.openai_temperature,
        timeout=settings.openai_timeout,
        max_retries=settings.openai_max_retries,
        **options,
    )


def default_graph_config(tools_available: bool = False) -> dict:
    """Return the graph used until an administrator saves a custom one.

    The default flow is ``system -> retrieval -> agent -> review -> end`` with a
    retry edge back to the agent, which makes both the knowledge-grounded reply
    and the review gate demonstrable on a fresh deployment. When tools are
    enabled a tools node and a tool-call route are added as well.
    """
    nodes: list[dict] = [
        {"id": "__start__", "type": "start", "config": {}},
        {
            "id": "system_node",
            "type": "system",
            "config": {"system_prompt": DEFAULT_SYSTEM_PROMPT},
        },
        {
            "id": "retrieval_node",
            "type": "retrieval",
            "config": {"top_k": 4, "min_score": 0.12},
        },
        {"id": "agent_node", "type": "agent", "config": {}},
        {
            "id": "review_node",
            "type": "review",
            "config": {
                "on_block": "fallback",
                "max_retries": 0,
                "fallback_message": DEFAULT_FALLBACK_MESSAGE,
            },
        },
        {"id": "__end__", "type": "end", "config": {}},
    ]
    edges: list[dict] = [
        {"source": "__start__", "target": "system_node"},
        {"source": "system_node", "target": "retrieval_node"},
        {"source": "retrieval_node", "target": "agent_node"},
        {"source": "agent_node", "target": "review_node", "condition": "respond"},
        {"source": "review_node", "target": "__end__", "condition": "pass"},
        {"source": "review_node", "target": "agent_node", "condition": "block"},
    ]
    if tools_available:
        nodes.insert(-1, {"id": "tools_node", "type": "tools", "config": {}})
        edges.extend(
            [
                {"source": "agent_node", "target": "tools_node", "condition": "tool_call"},
                {"source": "tools_node", "target": "agent_node"},
            ]
        )
    return {"nodes": nodes, "edges": edges}


def _has_system_prompt(graph_config: dict) -> bool:
    return any(
        node.get("type") == "system"
        and ((node.get("config") or {}).get("system_prompt") or "").strip()
        for node in graph_config.get("nodes", [])
    )


def _validate_sanitize_node(node: dict, settings: Settings) -> str | None:
    """Validate one sanitize node, including provider environment readiness."""
    config = node.get("config") or {}
    prefix = f"sanitize node {node.get('id')!r}: "
    error = validate_sanitize_provider_config(config)
    if error is not None:
        return prefix + error
    if parse_bool_setting(config.get("provider_enabled")) is not True:
        return None
    raw_provider = config.get("provider") or settings.moderation_provider
    provider = canonical_provider(raw_provider)
    if provider is None:
        return prefix + f"unknown moderation provider: {raw_provider!r}"
    try:
        resolve_provider_base_url(provider, config, settings)
    except ValueError as exc:
        return prefix + str(exc)
    if parse_bool_setting(config.get("provider_fail_open")) is False:
        missing = provider_credentials_error(provider, settings)
        if missing:
            # Fail-closed is a safety promise: refuse to save a graph that
            # would bypass the provider because a credential is missing.
            return prefix + f"provider_fail_open=false requires {missing}"
    return None


def validate_graph_config(
    graph_config: dict | None = None, settings: Settings | None = None
) -> str | None:
    """Compile the graph and check that it defines an agent role.

    Also validates every sanitize node's provider settings so a graph that
    claims provider moderation but cannot actually call the provider is
    rejected instead of silently passing replies.

    Returns an error message, or ``None`` when the configuration is usable.
    """
    effective_settings = settings or get_settings()
    try:
        LangGraphPipeline(graph_config=graph_config, settings=effective_settings)
    except Exception as exc:
        return f"The graph could not be compiled: {exc}"
    if graph_config is None:
        return None
    if not _has_system_prompt(graph_config):
        return "The graph needs a 'system' node with a non-empty prompt so the agent has a role."
    for node in graph_config.get("nodes", []):
        if node.get("type") != "sanitize":
            continue
        error = _validate_sanitize_node(node, effective_settings)
        if error is not None:
            return error
    return None


def create_pipeline(
    graph_config: dict | None = None, settings: Settings | None = None
) -> LangGraphPipeline:
    """Create a pipeline for the given configuration (defaults when omitted)."""
    if settings is None:
        return LangGraphPipeline(graph_config=graph_config)
    return LangGraphPipeline(graph_config=graph_config, settings=settings)

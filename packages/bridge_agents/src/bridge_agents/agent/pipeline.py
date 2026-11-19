"""Graph-driven agent runtime built on LangGraph.

The graph is described by JSON (nodes plus edges) and can be replaced at
runtime through the admin API. Seven node kinds are supported: ``system``
(inject a role prompt), ``retrieval`` (look up knowledge base passages),
``agent`` (the reply model), ``tools`` (execute tool calls), ``custom`` (an
extra model step with its own prompt), ``sanitize`` (mask banned words) and
``review`` (gate the reply before it reaches the customer).

Two built-in safety properties drive the design:

* tokens from any node other than ``agent``/``custom`` are never streamed to the
  customer (the reviewer must not leak its reasoning);
* as long as the graph contains a ``review`` node, streamed text is buffered and
  only released once the reviewer accepts the reply, so a rejected draft is
  never visible.

The graph is compiled without a checkpointer: conversation history is supplied
by the caller on every turn.
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import Annotated, Any, TypedDict
from uuid import uuid4

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from bridge_agents.agent import AgentPipeline
from bridge_agents.agent.prompts import DEFAULT_FALLBACK_MESSAGE, DEFAULT_REVIEW_PROMPT
from bridge_agents.agent.tools import get_tools
from bridge_agents.config import Settings, get_settings
from bridge_agents.moderation import ModerationError, Moderator, create_moderator
from bridge_agents.rag.format import format_context_blocks
from bridge_agents.rag.knowledge import KnowledgeBase, get_knowledge

LOGGER = logging.getLogger(__name__)

_IMAGE_PLACEHOLDER = "[image]"
_REVIEW_NODE_KINDS = frozenset({"review"})
_REPLY_NODE_KINDS = frozenset({"agent", "custom"})
_RETRIEVAL_NODE_KINDS = frozenset({"retrieval"})
_CONTEXT_MESSAGE_ID = "retrieval-context"


class _GraphState(TypedDict):
    """Internal LangGraph state; messages use the add_messages reducer."""

    messages: Annotated[list, add_messages]
    retrieved: list[dict]
    retrieved_context: str


def _first_system_prompt(graph_config: dict) -> str:
    """Return the first non-empty system prompt defined by the graph."""
    for node in graph_config.get("nodes", []):
        if node.get("type") != "system":
            continue
        prompt = (node.get("config", {}) or {}).get("system_prompt") or ""
        if prompt.strip():
            return prompt.strip()
    return ""


def _int_setting(value: Any, fallback: int, *, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, parsed)


def _float_setting(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _inject_retrieval_context(messages: list, context: str) -> list:
    """Insert (or refresh) the retrieved-knowledge system message.

    A stable message id keeps retries from stacking duplicate context blocks:
    LangGraph's ``add_messages`` reducer replaces a message with the same id.
    The context is placed after any leading role prompt so the model reads its
    role first and the retrieved evidence second.
    """
    if not context:
        return messages
    context_message = SystemMessage(content=context, id=_CONTEXT_MESSAGE_ID)
    for index, message in enumerate(messages):
        if getattr(message, "id", None) == _CONTEXT_MESSAGE_ID:
            return messages[:index] + [context_message] + messages[index + 1 :]
    insert_at = 0
    for index, message in enumerate(messages):
        if getattr(message, "type", "") == "system":
            insert_at = index + 1
        else:
            break
    return messages[:insert_at] + [context_message] + messages[insert_at:]


def _parse_verdict(content: Any) -> bool:
    """Interpret the reviewer's answer; malformed output defaults to accepted."""
    text = content if isinstance(content, str) else str(content)
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        lowered = text.lower()
        return "normal" in lowered and "false" not in lowered
    if isinstance(payload, dict):
        return bool(payload.get("normal", True))
    return True


def _blocked_attempts(messages: list) -> int:
    """Count rejected assistant drafts since the latest customer message."""
    attempts = 0
    for message in reversed(messages):
        if getattr(message, "type", "") == "human":
            break
        if isinstance(message, AIMessage) and (getattr(message, "response_metadata", {}) or {}).get(
            "review_blocked"
        ):
            attempts += 1
    return attempts


async def _complete_model(model: Any, messages: list, config: RunnableConfig | None = None) -> Any:
    """Run one model call, streaming when possible.

    Streaming the call (instead of a single ``ainvoke``) is what lets the
    graph's ``messages`` stream mode forward token chunks to the client.
    Aggregating the chunks yields the same final message shape.
    """
    stream = getattr(model, "astream", None)
    if stream is not None:
        combined: Any = None
        async for chunk in stream(messages, config=config):
            combined = chunk if combined is None else combined + chunk
        if combined is not None:
            return combined
    return await model.ainvoke(messages, config=config)


class LangGraphPipeline(AgentPipeline):
    """Compile a JSON graph into a runnable agent pipeline."""

    def __init__(
        self,
        graph_config: dict | None = None,
        *,
        llm: Any | None = None,
        tools: list | None = None,
        knowledge: KnowledgeBase | None = None,
        settings: Settings | None = None,
        moderator: Moderator | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._moderator = moderator
        if llm is None:
            from bridge_agents.agent.factory import build_chat_model

            llm = build_chat_model(self._settings)
        self._chat_model = llm
        self._tools = list(tools) if tools is not None else get_tools()
        self._tool_runner = ToolNode(self._tools) if self._tools else None
        self._knowledge = knowledge
        if graph_config is None:
            from bridge_agents.agent.factory import default_graph_config

            graph_config = default_graph_config(bool(self._tools))
        self._graph_config = graph_config
        self._nodes = {node["id"]: node for node in self._graph_config.get("nodes", [])}
        self._role_prompt = _first_system_prompt(self._graph_config)
        self._bound_tools = self._select_bound_tools()
        self._reply_node_ids = {
            node["id"] for node in self._nodes.values() if node["type"] in _REPLY_NODE_KINDS
        }
        self._review_node_ids = {
            node["id"] for node in self._nodes.values() if node["type"] in _REVIEW_NODE_KINDS
        }
        self._retrieval_node_ids = {
            node["id"] for node in self._nodes.values() if node["type"] in _RETRIEVAL_NODE_KINDS
        }
        self._compiled = self._assemble().compile()
        LOGGER.info(
            "agent graph compiled with %d node(s); tools bound=%d",
            len(self._nodes),
            len(self._bound_tools),
        )

    # -- graph construction -------------------------------------------------

    def _assemble(self) -> StateGraph:
        """Turn the JSON description into a LangGraph state graph."""
        builder = StateGraph(_GraphState)
        for node in self._graph_config.get("nodes", []):
            if node["type"] in ("start", "end"):
                continue
            builder.add_node(node["id"], self._node_for(node))

        plain_edges: list[dict] = []
        conditional_edges: dict[str, list[dict]] = {}
        for edge in self._graph_config.get("edges", []):
            if edge.get("condition"):
                conditional_edges.setdefault(edge["source"], []).append(edge)
            else:
                plain_edges.append(edge)

        for edge in plain_edges:
            builder.add_edge(self._graph_ref(edge["source"]), self._graph_ref(edge["target"]))

        for source, edges in conditional_edges.items():
            route_map = {
                self._graph_ref(edge["target"]): self._graph_ref(edge["target"]) for edge in edges
            }
            route_map[END] = END
            builder.add_conditional_edges(self._graph_ref(source), self._router(source), route_map)
        return builder

    @staticmethod
    def _graph_ref(node_id: str) -> str:
        """Translate pseudo node ids into LangGraph start/end constants."""
        if node_id == "__start__":
            return START
        if node_id == "__end__":
            return END
        return node_id

    def _node_for(self, node: dict) -> Any:
        """Build the callable (or runnable) for one configured node."""
        node_type = node["type"]
        config = node.get("config", {}) or {}
        if node_type == "agent":
            return self._agent_node
        if node_type == "retrieval":
            return self._make_retrieval_node(config)
        if node_type == "tools":
            return self._make_tool_node(config) or self._noop_node
        if node_type == "custom":
            return self._make_custom_node(config)
        if node_type == "system":
            return self._make_system_node(config)
        if node_type == "sanitize":
            return self._make_sanitize_node(config)
        if node_type == "review":
            return self._make_review_node(config)
        return self._noop_node

    @staticmethod
    def _noop_node(state: _GraphState) -> dict:
        return {}

    def _knowledge_base(self) -> KnowledgeBase | None:
        """Return the knowledge base, or None when retrieval is turned off."""
        if not self._settings.rag_enabled:
            return None
        if self._knowledge is None:
            self._knowledge = get_knowledge()
        return self._knowledge

    @staticmethod
    def _last_question(messages: list) -> str:
        """Return the most recent customer text from the graph messages."""
        for message in reversed(messages):
            if getattr(message, "type", "") != "human":
                continue
            content = getattr(message, "content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    str(part.get("text", ""))
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
        return ""

    def _make_retrieval_node(self, config: dict):
        """Create a node that looks up knowledge passages for the last question."""
        top_k = _int_setting(config.get("top_k"), self._settings.rag_top_k, minimum=1)
        min_score = _float_setting(config.get("min_score"), self._settings.rag_min_score)
        max_chars = _int_setting(
            config.get("max_chars"), self._settings.rag_max_context_chars, minimum=200
        )

        async def retrieval_node(state: _GraphState) -> dict:
            question = self._last_question(state.get("messages", []))
            if not question.strip():
                return {"retrieved": [], "retrieved_context": ""}
            knowledge = self._knowledge_base()
            if knowledge is None:
                return {"retrieved": [], "retrieved_context": ""}
            try:
                hits = await asyncio.to_thread(
                    knowledge.search, question, top_k=top_k, min_score=min_score
                )
            except Exception:
                LOGGER.exception("retrieval failed; continuing without knowledge context")
                return {"retrieved": [], "retrieved_context": ""}
            entries = [hit.chunk.as_dict() for hit in hits]
            context = format_context_blocks(entries, max_chars=max_chars)
            LOGGER.info("retrieval matched %d passage(s) for the question", len(entries))
            return {"retrieved": entries, "retrieved_context": context}

        return retrieval_node

    def _make_tool_node(self, config: dict) -> ToolNode | None:
        """Build a ToolNode restricted to the tools selected by the node."""
        if not self._tools:
            return None
        selected = config.get("tools")
        if isinstance(selected, list) and selected:
            filtered = [tool for tool in self._tools if getattr(tool, "name", "") in selected]
            return ToolNode(filtered) if filtered else None
        return self._tool_runner

    def _make_system_node(self, config: dict):
        """Create a node that injects a system message without calling a model."""
        prompt = (config.get("system_prompt") or "").strip()

        async def system_node(state: _GraphState) -> dict:
            if not prompt:
                return {}
            messages = list(state.get("messages", []))
            if any(getattr(message, "type", "") == "system" for message in messages):
                return {}
            return {"messages": [SystemMessage(content=prompt)]}

        return system_node

    def _make_custom_node(self, config: dict):
        """Create a model call with its own prompt; state keeps only the answer."""
        prompt = (config.get("system_prompt") or "").strip()

        async def custom_node(state: _GraphState, config: RunnableConfig | None = None) -> dict:
            messages = list(state.get("messages", []))
            if prompt:
                messages = [SystemMessage(content=prompt)] + [
                    message for message in messages if getattr(message, "type", "") != "system"
                ]
            try:
                response = await _complete_model(self._chat_model, messages, config)
                return {"messages": [response]}
            except Exception:
                LOGGER.exception("custom node could not call the model")
                return {"messages": [AIMessage(content="Sorry, I could not complete that step.")]}

        return custom_node

    def _make_sanitize_node(self, config: dict):
        """Create a node that masks banned words and optionally calls a provider.

        The local list is the hard gate and applies to every string message.
        The provider check is best-effort and applies to the latest assistant
        draft only, so conversation history is not re-classified on every turn.
        """
        raw_words = config.get("banned_words")
        if isinstance(raw_words, str):
            words = [word.strip() for word in raw_words.split(",") if word.strip()]
        elif isinstance(raw_words, list):
            words = [str(word).strip() for word in raw_words if str(word).strip()]
        else:
            words = []
        mask = re.compile("|".join(re.escape(word) for word in words)) if words else None
        replacement = config.get("replacement") or "***"

        provider_enabled = bool(config.get("provider_enabled"))
        provider_fallback = str(
            config.get("provider_fallback")
            or "This reply was blocked by the provider moderation service."
        )
        provider_fail_open = config.get("provider_fail_open", True) is not False
        moderator = self._moderator
        if provider_enabled and moderator is None:
            provider = (
                str(config.get("provider") or self._settings.moderation_provider or "openai")
                .strip()
                .lower()
            )
            timeout = _float_setting(
                config.get("provider_timeout"),
                float(self._settings.moderation_timeout),
            )
            if provider == "azure":
                base_url = str(
                    config.get("provider_base_url") or self._settings.moderation_azure_endpoint
                ).strip()
                api_key = str(
                    self._settings.moderation_azure_key or self._settings.moderation_api_key
                )
                api_version = str(
                    config.get("provider_api_version")
                    or self._settings.moderation_azure_api_version
                )
                severity = _int_setting(
                    config.get("provider_severity"),
                    self._settings.moderation_azure_severity,
                    minimum=0,
                )
                if base_url and api_key:
                    moderator = create_moderator(
                        "azure",
                        base_url=base_url,
                        api_key=api_key,
                        timeout=timeout,
                        api_version=api_version,
                        severity_threshold=severity,
                    )
                else:
                    LOGGER.warning("sanitize node: Azure endpoint/key is incomplete")
            elif provider == "perspective":
                base_url = str(config.get("provider_base_url") or "").strip()
                api_key = str(
                    self._settings.moderation_perspective_key or self._settings.moderation_api_key
                )
                threshold = _float_setting(
                    config.get("provider_threshold"),
                    self._settings.moderation_perspective_threshold,
                )
                if api_key:
                    moderator = create_moderator(
                        "perspective",
                        base_url=base_url,
                        api_key=api_key,
                        timeout=timeout,
                        threshold=threshold,
                        language=str(config.get("provider_language") or "en"),
                    )
                else:
                    LOGGER.warning(
                        "sanitize node requested Perspective but no API key is configured"
                    )
            elif provider in ("aliyun", "alibaba", "aliyun-green", "green"):
                region = str(
                    config.get("provider_region")
                    or self._settings.moderation_aliyun_region
                    or "cn-shanghai"
                ).strip()
                base_url = str(
                    config.get("provider_base_url")
                    or self._settings.moderation_aliyun_endpoint
                    or f"https://green-cip.{region}.aliyuncs.com"
                ).strip()
                access_key_id = self._settings.moderation_aliyun_access_key_id
                access_key_secret = self._settings.moderation_aliyun_access_key_secret
                service = str(
                    config.get("provider_service")
                    or self._settings.moderation_aliyun_service
                    or "comment_detection"
                )
                if access_key_id and access_key_secret:
                    moderator = create_moderator(
                        "aliyun",
                        base_url=base_url,
                        access_key_id=access_key_id,
                        access_key_secret=access_key_secret,
                        service=service,
                        timeout=timeout,
                        region=region,
                    )
                else:
                    LOGGER.warning("sanitize node: Alibaba Cloud AccessKey is not configured")
            elif provider in ("tencent", "tms", "tencent-tms"):
                region = str(
                    config.get("provider_region")
                    or self._settings.moderation_tencent_region
                    or "ap-guangzhou"
                ).strip()
                base_url = str(
                    config.get("provider_base_url")
                    or self._settings.moderation_tencent_endpoint
                    or "https://tms.tencentcloudapi.com"
                ).strip()
                secret_id = self._settings.moderation_tencent_secret_id
                secret_key = self._settings.moderation_tencent_secret_key
                biz_type = str(
                    config.get("provider_biz_type")
                    or self._settings.moderation_tencent_biz_type
                    or ""
                )
                if secret_id and secret_key:
                    moderator = create_moderator(
                        "tencent",
                        base_url=base_url,
                        access_key_id=secret_id,
                        access_key_secret=secret_key,
                        region=region,
                        biz_type=biz_type,
                        timeout=timeout,
                    )
                else:
                    LOGGER.warning(
                        "sanitize node: Tencent Cloud SecretId/SecretKey is not configured"
                    )
            elif provider in ("openai", "openai-compatible", "openai_compatible"):
                base_url = str(
                    config.get("provider_base_url")
                    or self._settings.moderation_base_url
                    or self._settings.openai_base_url
                ).strip()
                api_key = str(self._settings.moderation_api_key or self._settings.openai_api_key)
                if base_url:
                    moderator = create_moderator(
                        "openai",
                        base_url=base_url,
                        api_key=api_key,
                        model=str(config.get("provider_model") or self._settings.moderation_model),
                        timeout=timeout,
                    )
                else:
                    LOGGER.warning("sanitize node: moderation base URL is missing")
            else:
                LOGGER.warning("sanitize node: unknown moderation provider %r", provider)

        async def sanitize_node(state: _GraphState) -> dict:
            if mask is None and not (provider_enabled and moderator is not None):
                return {}
            messages = state.get("messages", [])
            latest_ai_id: str | None = None
            for message in messages:
                if isinstance(message, AIMessage) and message.id:
                    latest_ai_id = message.id
            repaired: list = []
            for message in messages:
                content = getattr(message, "content", None)
                if not isinstance(content, str):
                    continue
                cleaned = mask.sub(replacement, content) if mask is not None else content
                if (
                    provider_enabled
                    and moderator is not None
                    and isinstance(message, AIMessage)
                    and message.id == latest_ai_id
                    and cleaned.strip()
                ):
                    try:
                        verdict = await moderator.check(cleaned)
                    except ModerationError:
                        LOGGER.warning(
                            "provider moderation failed; %s",
                            "failing open" if provider_fail_open else "using fallback",
                        )
                        if not provider_fail_open:
                            cleaned = provider_fallback
                    else:
                        if verdict.flagged:
                            LOGGER.warning(
                                "provider moderation flagged the latest reply: %s",
                                verdict.reason or "flagged",
                            )
                            cleaned = provider_fallback
                if cleaned != content:
                    # Keep the message id so the reducer replaces the original.
                    repaired.append(message.model_copy(update={"content": cleaned}))
            return {"messages": repaired} if repaired else {}

        return sanitize_node

    def _make_review_node(self, config: dict):
        """Create the reply gate: buffer until accepted, retry or replace."""
        judge_prompt = config.get("system_prompt") or DEFAULT_REVIEW_PROMPT
        fallback_text = config.get("fallback_message") or DEFAULT_FALLBACK_MESSAGE
        blocked_behavior = config.get("on_block") or "fallback"
        try:
            retry_limit = int(config.get("max_retries", 0))
        except (TypeError, ValueError):
            retry_limit = 0

        async def review_node(state: _GraphState) -> dict:
            messages = list(state.get("messages", []))
            drafts = [message for message in messages if isinstance(message, AIMessage)]
            if not drafts:
                return {"messages": []}
            latest = drafts[-1]
            try:
                judgement = await self._chat_model.ainvoke(
                    [
                        SystemMessage(content=judge_prompt),
                        HumanMessage(content=str(latest.content)),
                    ]
                )
                accepted = _parse_verdict(judgement.content)
            except Exception:
                LOGGER.exception("review node could not judge the reply; accepting it")
                return {"messages": []}
            if accepted:
                LOGGER.info("review accepted the reply")
                return {"messages": []}

            attempt = _blocked_attempts(messages) + 1
            LOGGER.warning(
                "review rejected the reply (attempt %d, retry limit %d)", attempt, retry_limit
            )
            if attempt > retry_limit:
                if blocked_behavior == "pass_through":
                    LOGGER.info("review retry budget spent; forwarding the reply unchanged")
                    return {"messages": []}
                return {
                    "messages": [
                        AIMessage(
                            id=latest.id,
                            content=fallback_text,
                            response_metadata={"review_fallback": True},
                        )
                    ]
                }
            attempt_metadata = {
                **(getattr(latest, "response_metadata", {}) or {}),
                "review_blocked": True,
                "review_retry": True,
            }
            return {
                "messages": [
                    AIMessage(
                        id=latest.id,
                        content=latest.content,
                        response_metadata=attempt_metadata,
                    )
                ]
            }

        return review_node

    # -- routing ------------------------------------------------------------

    def _router(self, source: str):
        """Return a router that picks the configured conditional target."""

        def route(state: _GraphState) -> str:
            key = self._route_key(source, state)
            for edge in self._graph_config.get("edges", []):
                if edge["source"] == source and edge.get("condition") == key:
                    return self._graph_ref(edge["target"])
            return END

        return route

    def _route_key(self, node_id: str, state: _GraphState) -> str | None:
        """Map the current state to a route key for the given node."""
        node = self._nodes.get(node_id)
        if node is None:
            return None
        messages = state.get("messages", [])
        last = messages[-1] if messages else None
        if node["type"] == "agent":
            return "tool_call" if getattr(last, "tool_calls", None) else "respond"
        if node["type"] == "review":
            metadata = getattr(last, "response_metadata", {}) or {}
            return (
                "block"
                if isinstance(last, AIMessage) and metadata.get("review_blocked")
                else "pass"
            )
        return None

    def _select_bound_tools(self) -> list:
        """Return tools bound to agent nodes; empty unless a tool route exists."""
        if not self._tools:
            return []
        has_tool_route = any(
            edge.get("condition") == "tool_call"
            and (self._nodes.get(edge["source"]) or {}).get("type") == "agent"
            for edge in self._graph_config.get("edges", [])
        )
        if not has_tool_route:
            return []
        selected: set[str] = set()
        bind_all = False
        for node in self._graph_config.get("nodes", []):
            if node["type"] != "tools":
                continue
            node_tools = (node.get("config", {}) or {}).get("tools")
            if isinstance(node_tools, list) and node_tools:
                selected.update(str(name) for name in node_tools)
            else:
                bind_all = True
        if bind_all:
            return list(self._tools)
        return [tool for tool in self._tools if getattr(tool, "name", "") in selected]

    # -- model nodes --------------------------------------------------------

    async def _agent_node(self, state: _GraphState, config: RunnableConfig | None = None) -> dict:
        """Call the reply model, binding tools only when the graph routes them."""
        messages = _inject_retrieval_context(
            list(state.get("messages", [])), state.get("retrieved_context") or ""
        )
        try:
            model = (
                self._chat_model.bind_tools(self._bound_tools)
                if self._bound_tools
                else self._chat_model
            )
            response = await _complete_model(model, messages, config)
            LOGGER.info(
                "agent reply generated (tool_calls=%s)", bool(getattr(response, "tool_calls", None))
            )
            return {"messages": [response]}
        except Exception as exc:
            LOGGER.exception("agent node could not call the model")
            return {
                "messages": [
                    AIMessage(
                        content="Sorry, something went wrong while generating a reply.",
                        response_metadata={"is_error": True, "error_detail": str(exc)},
                    )
                ]
            }

    # -- AgentPipeline interface -------------------------------------------

    @staticmethod
    def _to_langchain_messages(raw_messages: list[dict], system_prompt: str = "") -> list:
        """Convert OpenAI-style history into LangChain messages.

        When a role prompt is supplied it becomes the leading system message.
        Every message gets an explicit id so streaming can tell input history
        apart from newly generated content.
        """
        converted: list = []
        if system_prompt:
            converted.append(SystemMessage(content=system_prompt, id=str(uuid4())))
        for raw in raw_messages:
            role = raw.get("role", "")
            if role == "user":
                content = raw.get("content", "")
                images = raw.get("images", [])
                text = (
                    ""
                    if isinstance(content, str) and content.startswith(_IMAGE_PLACEHOLDER)
                    else content
                )
                if images:
                    parts: list[dict] = []
                    if text:
                        parts.append({"type": "text", "text": text})
                    for image_url in images:
                        parts.append({"type": "image_url", "image_url": {"url": image_url}})
                    converted.append(HumanMessage(content=parts, id=str(uuid4())))
                else:
                    converted.append(HumanMessage(content=text, id=str(uuid4())))
            elif role == "assistant":
                converted.append(AIMessage(content=raw.get("content", ""), id=str(uuid4())))
        return converted

    async def invoke(self, state: dict, config: dict | None = None) -> dict:
        """Run the graph to completion and return the rendered history."""
        incoming = state.get("messages", [])
        graph_state = {"messages": self._to_langchain_messages(incoming, self._role_prompt)}
        final_state = await self._compiled.ainvoke(graph_state, config)

        rendered: list[dict] = []
        for message in final_state.get("messages", []):
            metadata = getattr(message, "response_metadata", {}) or {}
            if metadata.get("review_blocked"):
                continue
            message_type = getattr(message, "type", "")
            if message_type in ("system", "tool"):
                continue
            if message_type == "ai" and getattr(message, "tool_calls", None):
                continue
            content = getattr(message, "content", None)
            if content is None and isinstance(message, dict):
                content = message.get("content", "")
            rendered.append(
                {
                    "role": "user" if message_type == "human" else "assistant",
                    "content": content or "",
                }
            )
        return {**state, "messages": rendered}

    async def stream(self, state: dict, config: dict | None = None) -> AsyncGenerator[dict, None]:
        """Stream one turn, holding text back while the review gate is closed."""
        incoming = state.get("messages", [])
        graph_messages = self._to_langchain_messages(incoming, self._role_prompt)
        history_ids = {message.id for message in graph_messages}
        graph_state = {"messages": graph_messages}

        yield {**state, "phase": "start"}

        reply_parts: dict[str, str] = {}
        gate_active = bool(self._review_node_ids)
        gate_open = False

        async for mode, payload in self._compiled.astream(
            graph_state, config, stream_mode=["updates", "messages"]
        ):
            if mode == "messages":
                chunk, metadata = payload
                if not isinstance(chunk, AIMessageChunk) or chunk.id is None:
                    continue
                if (metadata or {}).get("langgraph_node") not in self._reply_node_ids:
                    continue
                if getattr(chunk, "tool_call_chunks", None):
                    continue
                text = chunk.content if isinstance(chunk.content, str) else ""
                if not text:
                    continue
                reply_parts[chunk.id] = reply_parts.get(chunk.id, "") + text
                if gate_active and not gate_open:
                    continue
                yield {
                    **state,
                    "messages": list(incoming)
                    + [{"role": "assistant", "content": "".join(reply_parts.values())}],
                    "phase": "streaming",
                }
                continue

            for node_name, node_output in (payload or {}).items():
                if node_name in self._retrieval_node_ids and node_output:
                    sources = node_output.get("retrieved")
                    if sources is not None:
                        yield {
                            **state,
                            "phase": "retrieval",
                            "sources": sources,
                        }
                produced = node_output.get("messages", []) if node_output else []
                for message in produced:
                    if isinstance(message, ToolMessage):
                        yield {
                            **state,
                            "phase": "tool_call",
                            "tool_name": getattr(message, "name", "unknown"),
                            "tool_result": getattr(message, "content", ""),
                        }
                changed = False
                for message in produced:
                    if not isinstance(message, AIMessage) or message.id in history_ids:
                        continue
                    metadata = getattr(message, "response_metadata", {}) or {}
                    if metadata.get("review_blocked"):
                        reply_parts.pop(message.id, None)
                        continue
                    if getattr(message, "tool_calls", None):
                        reply_parts.pop(message.id, None)
                        continue
                    if not message.content:
                        continue
                    reply_parts[message.id] = (
                        message.content
                        if isinstance(message.content, str)
                        else str(message.content)
                    )
                    if not metadata.get("is_error"):
                        changed = True
                if node_name in self._review_node_ids:
                    blocked = any(
                        isinstance(message, AIMessage)
                        and (getattr(message, "response_metadata", {}) or {}).get("review_blocked")
                        for message in produced
                    )
                    if blocked:
                        gate_open = False
                    else:
                        gate_open = True
                        changed = changed or bool(reply_parts)
                if changed and (not gate_active or gate_open):
                    yield {
                        **state,
                        "messages": list(incoming)
                        + [{"role": "assistant", "content": "".join(reply_parts.values())}],
                        "phase": "streaming",
                    }

        yield {
            **state,
            "messages": list(incoming)
            + [{"role": "assistant", "content": "".join(reply_parts.values())}],
            "phase": "done",
        }

    def get_mermaid_diagram(self) -> str:
        """Return the compiled graph rendered as Mermaid source."""
        return self._compiled.get_graph().draw_mermaid()

    def get_graph_config(self) -> dict:
        """Return the configuration this pipeline was built from."""
        return self._graph_config

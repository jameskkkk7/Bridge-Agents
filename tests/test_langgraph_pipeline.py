"""Behaviour contract of the editable LangGraph pipeline."""

from __future__ import annotations

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.core.agent.factory import validate_graph_config
from app.core.agent.langgraph_pipeline import (
    LangGraphPipeline,
    _blocked_attempts,
    _parse_verdict,
)
from app.core.agent.prompts import DEFAULT_SYSTEM_PROMPT


def _review_graph_config() -> dict:
    return {
        "nodes": [
            {"id": "__start__", "type": "start", "config": {}},
            {
                "id": "system_node",
                "type": "system",
                "config": {"system_prompt": "You are a helpful assistant."},
            },
            {"id": "agent_node", "type": "agent", "config": {}},
            {
                "id": "review_node",
                "type": "review",
                "config": {"on_block": "pass_through", "max_retries": 2},
            },
            {"id": "__end__", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "__start__", "target": "system_node"},
            {"source": "system_node", "target": "agent_node"},
            {
                "source": "agent_node",
                "target": "review_node",
                "condition": "respond",
                "source_handle": "output",
            },
            {
                "source": "review_node",
                "target": "__end__",
                "condition": "pass",
                "source_handle": "pass",
                "target_handle": "input",
            },
            {
                "source": "review_node",
                "target": "agent_node",
                "condition": "block",
                "source_handle": "block",
            },
        ],
    }


def _pipeline(config: dict | None = None) -> LangGraphPipeline:
    return LangGraphPipeline(graph_config=config, tools=[])


class _Judge:
    """Fake chat model returning a canned review verdict."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[list] = []

    async def ainvoke(self, messages, config=None, **kwargs):
        self.calls.append(list(messages))
        return AIMessage(content=self.content)


class _FakeCompiled:
    """Fake compiled graph yielding prepared (mode, payload) pairs."""

    def __init__(self, events: list[tuple[str, object]]) -> None:
        self.events = events
        self.seen_graph_state: dict | None = None

    async def astream(self, graph_state, config=None, stream_mode=None):
        self.seen_graph_state = graph_state
        for mode, payload in self.events:
            yield mode, payload

    async def ainvoke(self, graph_state, config=None):
        self.seen_graph_state = graph_state
        return {"messages": graph_state["messages"] + [AIMessage(content="final", id="final")]}


def _updates(node: str, messages: list) -> tuple[str, dict]:
    return "updates", {node: {"messages": messages}}


# --- validation and construction -------------------------------------------


def test_validate_graph_config_accepts_visual_handles() -> None:
    assert validate_graph_config(_review_graph_config()) is None


def test_pipeline_compiles_and_renders_configured_nodes() -> None:
    pipeline = _pipeline(_review_graph_config())
    diagram = pipeline.get_mermaid_diagram()
    assert "review_node" in diagram
    assert "agent_node" in diagram
    assert "system_node" in diagram


def test_validate_graph_config_requires_a_system_prompt() -> None:
    config = _review_graph_config()
    config["nodes"][1]["config"]["system_prompt"] = ""
    error = validate_graph_config(config)
    assert error is not None
    assert "system" in error.lower()


def test_validate_graph_config_requires_a_system_node() -> None:
    config = {
        "nodes": [
            {"id": "__start__", "type": "start", "config": {}},
            {"id": "agent_node", "type": "agent", "config": {}},
            {"id": "__end__", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "__start__", "target": "agent_node"},
            {"source": "agent_node", "target": "__end__", "condition": "respond"},
        ],
    }
    error = validate_graph_config(config)
    assert error is not None
    assert "system" in error.lower()


def test_default_graph_includes_the_review_gate() -> None:
    pipeline = _pipeline()
    node_ids = [node["id"] for node in pipeline.get_graph_config()["nodes"]]
    assert node_ids == [
        "__start__",
        "system_node",
        "retrieval_node",
        "agent_node",
        "review_node",
        "__end__",
    ]
    assert pipeline._role_prompt == DEFAULT_SYSTEM_PROMPT
    assert pipeline._review_node_ids == {"review_node"}
    assert pipeline._reply_node_ids == {"agent_node"}
    assert pipeline._retrieval_node_ids == {"retrieval_node"}
    diagram = pipeline.get_mermaid_diagram()
    assert "flowchart" in diagram or "graph TD" in diagram


def test_graph_config_round_trips() -> None:
    config = _review_graph_config()
    assert _pipeline(config).get_graph_config() == config


# --- review node ------------------------------------------------------------


def _review_pipeline() -> LangGraphPipeline:
    pipeline = _pipeline()
    pipeline._chat_model = _Judge('{"normal": false, "reason": "unsafe"}')
    return pipeline


def test_review_rejection_becomes_a_fallback_message() -> None:
    pipeline = _review_pipeline()
    node = pipeline._make_review_node({"max_retries": 0})
    messages = [HumanMessage(content="hi", id="h1"), AIMessage(content="bad reply", id="a1")]
    update = _run(node, {"messages": messages})
    replacement = update["messages"][0]
    assert isinstance(replacement, AIMessage)
    assert replacement.id == "a1"
    assert replacement.content != "bad reply"
    assert replacement.response_metadata["review_fallback"] is True


def test_review_pass_through_keeps_the_original_reply() -> None:
    pipeline = _review_pipeline()
    node = pipeline._make_review_node({"max_retries": 0, "on_block": "pass_through"})
    messages = [HumanMessage(content="hi", id="h1"), AIMessage(content="bad reply", id="a1")]
    assert _run(node, {"messages": messages}) == {"messages": []}


def test_review_marks_a_retry_when_budget_remains() -> None:
    pipeline = _review_pipeline()
    node = pipeline._make_review_node({"max_retries": 2})
    messages = [HumanMessage(content="hi", id="h1"), AIMessage(content="bad reply", id="a1")]
    update = _run(node, {"messages": messages})
    marked = update["messages"][0]
    assert marked.id == "a1"
    assert marked.content == "bad reply"
    assert marked.response_metadata["review_blocked"] is True
    assert marked.response_metadata["review_retry"] is True


def test_review_falls_back_once_the_retry_budget_is_spent() -> None:
    pipeline = _review_pipeline()
    node = pipeline._make_review_node({"max_retries": 2})
    messages = [
        HumanMessage(content="hi", id="h1"),
        AIMessage(content="draft one", id="a1", response_metadata={"review_blocked": True}),
        AIMessage(content="draft two", id="a2", response_metadata={"review_blocked": True}),
        AIMessage(content="draft three", id="a3"),
    ]
    update = _run(node, {"messages": messages})
    replacement = update["messages"][0]
    assert replacement.id == "a3"
    assert replacement.response_metadata["review_fallback"] is True


def test_review_accepts_and_keeps_the_gate_state_empty() -> None:
    pipeline = _pipeline()
    pipeline._chat_model = _Judge('{"normal": true}')
    node = pipeline._make_review_node({})
    messages = [HumanMessage(content="hi", id="h1"), AIMessage(content="fine", id="a1")]
    assert _run(node, {"messages": messages}) == {"messages": []}


def test_review_without_an_assistant_draft_is_a_noop() -> None:
    pipeline = _review_pipeline()
    node = pipeline._make_review_node({})
    assert _run(node, {"messages": [HumanMessage(content="hi", id="h1")]}) == {"messages": []}


def test_review_non_json_verdict_uses_keyword_fallback() -> None:
    pipeline = _pipeline()
    pipeline._chat_model = _Judge("This reply looks normal to me.")
    node = pipeline._make_review_node({})
    messages = [HumanMessage(content="hi", id="h1"), AIMessage(content="fine", id="a1")]
    assert _run(node, {"messages": messages}) == {"messages": []}

    pipeline._chat_model = _Judge("This reply is not normal: false")
    assert _run(node, {"messages": messages})["messages"][0].id == "a1"


def test_verdict_parser_handles_json_and_garbage() -> None:
    assert _parse_verdict('{"normal": true}') is True
    assert _parse_verdict('{"normal": false}') is False
    assert _parse_verdict("no idea") is False
    assert _parse_verdict("all normal, no issues") is True


def test_blocked_attempt_counter_stops_at_the_customer_message() -> None:
    messages = [
        HumanMessage(content="hi"),
        AIMessage(content="ok", response_metadata={"review_blocked": True}),
        AIMessage(content="retry", response_metadata={"review_blocked": True}),
    ]
    assert _blocked_attempts(messages) == 2
    messages.extend([HumanMessage(content="again"), AIMessage(content="final")])
    assert _blocked_attempts(messages) == 0


# --- other nodes ------------------------------------------------------------


def test_sanitize_node_reemits_only_modified_messages() -> None:
    pipeline = _pipeline()
    node = pipeline._make_sanitize_node({"banned_words": ["damn"], "replacement": "***"})
    messages = [
        HumanMessage(content="hi", id="h1"),
        AIMessage(content="clean reply", id="a1"),
        AIMessage(content="damn reply", id="a2"),
    ]
    update = _run(node, {"messages": messages})
    assert [message.id for message in update["messages"]] == ["a2"]
    assert update["messages"][0].content == "*** reply"
    assert _run(node, {"messages": [AIMessage(content="fine", id="a3")]}) == {}


def test_system_node_skips_when_a_system_message_already_exists() -> None:
    pipeline = _pipeline()
    node = pipeline._make_system_node({"system_prompt": "role"})
    existing = [SystemMessage(content="role", id="s1"), HumanMessage(content="hi", id="h1")]
    assert _run(node, {"messages": existing}) == {}
    assert (
        _run(node, {"messages": [HumanMessage(content="hi", id="h1")]})["messages"][0].content
        == "role"
    )


def test_custom_node_prompt_replaces_the_graph_prompt_for_its_call() -> None:
    pipeline = _pipeline()
    received: list[list] = []

    class _Model:
        async def ainvoke(self, messages, config=None, **kwargs):
            received.append(list(messages))
            return AIMessage(content="ok")

    pipeline._chat_model = _Model()
    node = pipeline._make_custom_node({"system_prompt": "You are a translator."})
    state = {
        "messages": [
            SystemMessage(content="global role", id="s1"),
            HumanMessage(content="hi", id="h1"),
        ]
    }
    update = _run(node, state)
    assert isinstance(received[0][0], SystemMessage)
    assert received[0][0].content == "You are a translator."
    assert all(message.content != "global role" for message in received[0])
    assert [message.content for message in update["messages"]] == ["ok"]


def test_agent_node_streams_when_the_model_supports_it() -> None:
    pipeline = _pipeline()

    class _StreamingModel:
        async def astream(self, messages, config=None):
            yield AIMessageChunk(content="Hello ")
            yield AIMessageChunk(content="world")

        async def ainvoke(self, messages, config=None):
            raise AssertionError("astream should be preferred")

    pipeline._chat_model = _StreamingModel()
    update = _run(pipeline._agent_node, {"messages": [HumanMessage(content="hi")]})
    assert update["messages"][0].content == "Hello world"


def test_agent_node_reports_model_failures() -> None:
    pipeline = _pipeline()

    class _Broken:
        async def ainvoke(self, messages, config=None, **kwargs):
            raise RuntimeError("model down")

    pipeline._chat_model = _Broken()
    update = _run(pipeline._agent_node, {"messages": [HumanMessage(content="hi")]})
    message = update["messages"][0]
    assert message.response_metadata["is_error"] is True
    assert "Sorry" in message.content


def test_custom_node_reports_model_failures() -> None:
    pipeline = _pipeline()

    class _Broken:
        async def ainvoke(self, messages, config=None, **kwargs):
            raise RuntimeError("model down")

    pipeline._chat_model = _Broken()
    node = pipeline._make_custom_node({})
    update = _run(node, {"messages": [HumanMessage(content="hi")]})
    assert "Sorry" in update["messages"][0].content


# --- routing and tool binding ----------------------------------------------


def test_router_keys_follow_message_metadata() -> None:
    pipeline = _pipeline(_review_graph_config())
    assert pipeline._route_key("agent_node", {"messages": [AIMessage(content="x")]}) == "respond"
    assert (
        pipeline._route_key(
            "agent_node",
            {
                "messages": [
                    AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "1"}])
                ]
            },
        )
        == "tool_call"
    )
    blocked = AIMessage(content="x", response_metadata={"review_blocked": True})
    assert pipeline._route_key("review_node", {"messages": [blocked]}) == "block"
    assert pipeline._route_key("review_node", {"messages": [AIMessage(content="x")]}) == "pass"
    assert pipeline._route_key("system_node", {"messages": []}) is None


def test_tools_are_not_bound_without_a_tool_route() -> None:
    class _FakeTool:
        name = "get_current_time"

    pipeline = _pipeline(_review_graph_config())
    pipeline._tools = [_FakeTool()]
    assert pipeline._select_bound_tools() == []


def test_bound_tools_are_the_union_of_tools_node_selections() -> None:
    class _FakeTool:
        def __init__(self, name: str) -> None:
            self.name = name

    config = {
        "nodes": [
            {"id": "__start__", "type": "start", "config": {}},
            {"id": "system_node", "type": "system", "config": {"system_prompt": "role"}},
            {"id": "agent_node", "type": "agent", "config": {}},
            {"id": "tools_node", "type": "tools", "config": {"tools": ["calculate"]}},
            {"id": "__end__", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "__start__", "target": "system_node"},
            {"source": "system_node", "target": "agent_node"},
            {"source": "agent_node", "target": "__end__", "condition": "respond"},
            {"source": "agent_node", "target": "tools_node", "condition": "tool_call"},
            {"source": "tools_node", "target": "agent_node"},
        ],
    }
    pipeline = _pipeline(config)
    pipeline._tools = [_FakeTool("calculate"), _FakeTool("get_current_time")]
    bound = pipeline._select_bound_tools()
    assert [tool.name for tool in bound] == ["calculate"]


def test_tool_node_can_be_restricted_to_selected_tools() -> None:
    from app.core.agent.tools import calculate, get_current_time

    config = {
        "nodes": [
            {"id": "__start__", "type": "start", "config": {}},
            {"id": "system_node", "type": "system", "config": {"system_prompt": "role"}},
            {"id": "agent_node", "type": "agent", "config": {}},
            {"id": "tools_node", "type": "tools", "config": {"tools": ["calculate"]}},
            {"id": "__end__", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "__start__", "target": "system_node"},
            {"source": "system_node", "target": "agent_node"},
            {"source": "agent_node", "target": "__end__", "condition": "respond"},
            {"source": "agent_node", "target": "tools_node", "condition": "tool_call"},
            {"source": "tools_node", "target": "agent_node"},
        ],
    }
    pipeline = LangGraphPipeline(config, tools=[calculate, get_current_time])
    tool_node = pipeline._make_tool_node({"tools": ["calculate"]})
    assert set(tool_node.tools_by_name) == {"calculate"}


# --- streaming --------------------------------------------------------------


def test_stream_replaces_reemitted_messages_instead_of_appending() -> None:
    pipeline = _pipeline(_review_graph_config())
    pipeline._compiled = _FakeCompiled(
        [
            _updates("agent_node", [AIMessage(content="hello damn world", id="new1")]),
            _updates("sanitize_node", [AIMessage(content="hello *** world", id="new1")]),
        ]
    )
    updates = _collect(pipeline.stream({"messages": [{"role": "user", "content": "hi"}]}))
    assert updates[-1]["phase"] == "done"
    assert updates[-1]["messages"][-1] == {"role": "assistant", "content": "hello *** world"}


def test_stream_holds_tokens_until_review_accepts() -> None:
    pipeline = _pipeline(_review_graph_config())
    chunk = AIMessageChunk(content="hello ", id="new1")
    pipeline._compiled = _FakeCompiled(
        [
            ("messages", (chunk, {"langgraph_node": "agent_node"})),
            _updates("agent_node", [AIMessage(content="hello world", id="new1")]),
            _updates("review_node", []),
        ]
    )
    updates = _collect(pipeline.stream({"messages": [{"role": "user", "content": "hi"}]}))
    streaming = [update for update in updates if update.get("phase") == "streaming"]
    assert len(streaming) == 1
    assert streaming[0]["messages"][-1]["content"] == "hello world"
    assert updates[0]["phase"] == "start"
    assert updates[-1]["phase"] == "done"


def test_stream_never_leaks_a_rejected_draft() -> None:
    pipeline = _pipeline(_review_graph_config())
    rejected = "you get a guaranteed refund"
    blocked_metadata = {"review_blocked": True}
    pipeline._compiled = _FakeCompiled(
        [
            _updates("agent_node", [AIMessage(content=rejected, id="a1")]),
            _updates(
                "review_node",
                [AIMessage(content=rejected, id="a1", response_metadata=blocked_metadata)],
            ),
            _updates(
                "agent_node", [AIMessage(content="Refunds follow the 14-day policy.", id="a2")]
            ),
            _updates("review_node", []),
        ]
    )
    updates = _collect(pipeline.stream({"messages": [{"role": "user", "content": "refund?"}]}))
    streamed_text = " ".join(
        update["messages"][-1]["content"] for update in updates if update.get("messages")
    )
    assert "guaranteed" not in streamed_text
    assert updates[-1]["messages"][-1]["content"] == "Refunds follow the 14-day policy."


def test_stream_reports_tool_calls() -> None:
    pipeline = _pipeline(_review_graph_config())
    pipeline._compiled = _FakeCompiled(
        [
            _updates(
                "tools_node",
                [
                    ToolMessage(
                        content="2026-01-01 00:00:00 UTC",
                        name="get_current_time",
                        tool_call_id="call-1",
                        id="tool-1",
                    )
                ],
            ),
            _updates("agent_node", [AIMessage(content="It is midnight UTC.", id="a1")]),
            _updates("review_node", []),
        ]
    )
    updates = _collect(pipeline.stream({"messages": [{"role": "user", "content": "time?"}]}))
    tool_updates = [update for update in updates if update.get("phase") == "tool_call"]
    assert tool_updates[0]["tool_name"] == "get_current_time"
    assert "UTC" in tool_updates[0]["tool_result"]
    assert updates[-1]["phase"] == "done"


# --- invoke and message conversion -----------------------------------------


def test_invoke_renders_only_the_visible_reply() -> None:
    pipeline = _pipeline(_review_graph_config())

    class _Compiled:
        async def ainvoke(self, graph_state, config=None):
            return {
                "messages": graph_state["messages"]
                + [
                    AIMessage(
                        content="draft",
                        id="draft",
                        response_metadata={"review_blocked": True},
                    ),
                    ToolMessage(content="result", tool_call_id="c1", id="tool-1"),
                    AIMessage(
                        content="preamble",
                        id="preamble",
                        tool_calls=[{"name": "calc", "args": {}, "id": "c2"}],
                    ),
                    AIMessage(content="final answer", id="final"),
                ]
            }

    pipeline._compiled = _Compiled()
    state = {"messages": [{"role": "user", "content": "hello"}]}
    result = _run(pipeline.invoke, state)
    assert result["messages"] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "final answer"},
    ]


def test_invoke_prepends_the_graph_role_prompt() -> None:
    pipeline = _pipeline(_review_graph_config())

    class _Compiled:
        captured: dict | None = None

        async def ainvoke(self, graph_state, config=None):
            self.captured = graph_state
            return {"messages": graph_state["messages"] + [AIMessage(content="ok", id="a1")]}

    compiled = _Compiled()
    pipeline._compiled = compiled
    state = {
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "previous"},
        ]
    }
    _run(pipeline.invoke, state)
    converted = compiled.captured["messages"]
    assert isinstance(converted[0], SystemMessage)
    assert converted[0].content == "You are a helpful assistant."
    assert isinstance(converted[1], HumanMessage)
    assert isinstance(converted[2], AIMessage)


def test_message_conversion_supports_images() -> None:
    raw_messages = [
        {"role": "user", "content": "Hello"},
        {
            "role": "user",
            "content": "[image] 12345678-1234-1234-1234-123456789abc",
            "images": ["data:image/png;base64,AAA"],
        },
        {
            "role": "user",
            "content": "What is in this image?",
            "images": ["data:image/png;base64,BBB"],
        },
    ]
    converted = LangGraphPipeline._to_langchain_messages(raw_messages)
    assert len(converted) == 3
    assert converted[0].content == "Hello"
    assert converted[1].content == [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}}
    ]
    assert converted[2].content == [
        {"type": "text", "text": "What is in this image?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,BBB"}},
    ]


def test_message_conversion_prepends_a_system_prompt() -> None:
    converted = LangGraphPipeline._to_langchain_messages(
        [{"role": "user", "content": "Hello"}], "You are a bot."
    )
    assert len(converted) == 2
    assert isinstance(converted[0], SystemMessage)
    assert converted[0].content == "You are a bot."
    assert isinstance(converted[1], HumanMessage)


# --- helpers ---------------------------------------------------------------


def _run(callable_or_fn, state):
    """Run one coroutine or node function synchronously in tests."""
    import asyncio

    result = callable_or_fn(state)
    if hasattr(result, "__await__"):
        return asyncio.run(result)
    raise TypeError("expected an awaitable")


def _collect(stream):
    import asyncio

    async def drain():
        return [update async for update in stream]

    return asyncio.run(drain())

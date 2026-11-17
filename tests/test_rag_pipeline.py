"""Retrieval grounding inside the LangGraph pipeline."""

from __future__ import annotations

from pathlib import Path

from bridge_agents.agent.pipeline import LangGraphPipeline
from bridge_agents.rag.embeddings import HashedEmbedder
from bridge_agents.rag.knowledge import KnowledgeBase
from langchain_core.messages import AIMessage, SystemMessage

DOCUMENT = """# Widget Pro

Widget Pro is the self-hosted support widget.

## Activation

Activate Widget Pro from Settings → Billing → Activate and confirm the licence key.
"""


class _AnswerModel:
    """Capture the messages the agent node sends and answer once."""

    def __init__(self) -> None:
        self.calls: list[list] = []

    async def ainvoke(self, messages, config=None, **kwargs):
        self.calls.append(list(messages))
        return AIMessage(content="Activate it from Settings [1].", id="draft")


def _knowledge(tmp_path: Path) -> KnowledgeBase:
    (tmp_path / "widget.md").write_text(DOCUMENT, encoding="utf-8")
    return KnowledgeBase(tmp_path, HashedEmbedder(), top_k=3, min_score=0.0)


def _graph_config() -> dict:
    return {
        "nodes": [
            {"id": "__start__", "type": "start", "config": {}},
            {
                "id": "system_node",
                "type": "system",
                "config": {"system_prompt": "You are a support assistant."},
            },
            {"id": "retrieval_node", "type": "retrieval", "config": {"top_k": 2}},
            {"id": "agent_node", "type": "agent", "config": {}},
            {"id": "__end__", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "__start__", "target": "system_node"},
            {"source": "system_node", "target": "retrieval_node"},
            {"source": "retrieval_node", "target": "agent_node"},
            {"source": "agent_node", "target": "__end__"},
        ],
    }


def _run(pipeline: LangGraphPipeline, question: str) -> list[dict]:
    async def drain():
        return [
            update
            async for update in pipeline.stream(
                {"messages": [{"role": "user", "content": question}]}
            )
        ]

    import asyncio

    return asyncio.run(drain())


def test_retrieval_node_injects_cited_context(tmp_path: Path) -> None:
    model = _AnswerModel()
    pipeline = LangGraphPipeline(
        graph_config=_graph_config(), llm=model, tools=[], knowledge=_knowledge(tmp_path)
    )

    updates = _run(pipeline, "How do I activate Widget Pro?")

    retrieval = [update for update in updates if update.get("phase") == "retrieval"]
    assert retrieval
    assert retrieval[0]["sources"][0]["citation"] == "Widget Pro — Activation"

    context_messages = [
        message
        for message in model.calls[0]
        if isinstance(message, SystemMessage) and "Retrieved knowledge" in str(message.content)
    ]
    assert len(context_messages) == 1
    assert "[1] Widget Pro — Activation" in str(context_messages[0].content)

    done = updates[-1]
    assert done["phase"] == "done"
    assert "Activate it from Settings" in done["messages"][-1]["content"]


def test_retrieval_context_sits_after_the_role_prompt(tmp_path: Path) -> None:
    model = _AnswerModel()
    pipeline = LangGraphPipeline(
        graph_config=_graph_config(), llm=model, tools=[], knowledge=_knowledge(tmp_path)
    )
    _run(pipeline, "activate widget")
    system_messages = [message for message in model.calls[0] if isinstance(message, SystemMessage)]
    assert system_messages[0].content == "You are a support assistant."
    assert "Retrieved knowledge" in str(system_messages[1].content)


def test_empty_knowledge_answers_without_context(tmp_path: Path) -> None:
    model = _AnswerModel()
    empty = KnowledgeBase(tmp_path / "missing", HashedEmbedder(), min_score=0.0)
    pipeline = LangGraphPipeline(graph_config=_graph_config(), llm=model, tools=[], knowledge=empty)

    updates = _run(pipeline, "How do I activate Widget Pro?")

    assert all(
        update.get("phase") != "retrieval" or update.get("sources") == [] for update in updates
    )
    assert not any(
        isinstance(message, SystemMessage) and "Retrieved knowledge" in str(message.content)
        for message in model.calls[0]
    )


def test_retrieval_can_be_disabled_by_settings(tmp_path: Path, monkeypatch) -> None:
    from bridge_agents.config import get_settings

    monkeypatch.setenv("RAG_ENABLED", "false")
    get_settings.cache_clear()
    try:
        model = _AnswerModel()
        pipeline = LangGraphPipeline(
            graph_config=_graph_config(), llm=model, tools=[], knowledge=_knowledge(tmp_path)
        )
        _run(pipeline, "activate widget")
        assert not any(
            isinstance(message, SystemMessage) and "Retrieved knowledge" in str(message.content)
            for message in model.calls[0]
        )
    finally:
        get_settings.cache_clear()

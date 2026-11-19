"""Embeddable, explicitly configured runtime facade.

Library users that do not need the HTTP server can drive the review-gated
pipeline directly::

    from bridge_agents.runtime import AgentRuntime

    async with AgentRuntime(llm=my_chat_model) as runtime:
        answer = await runtime.reply("How do I activate Widget Pro?")
        async for event in runtime.stream("Can I get a refund?"):
            ...

Configuration is explicit (``Settings`` or constructor arguments); nothing is
started or connected at import time.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from typing import Any

from bridge_agents.agent.pipeline import LangGraphPipeline
from bridge_agents.config import Settings, get_settings


class AgentRuntime:
    """A small, async-first façade over :class:`LangGraphPipeline`."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        graph_config: dict | None = None,
        llm: Any | None = None,
        tools: list | None = None,
        knowledge: Any | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._pipeline = LangGraphPipeline(
            graph_config,
            llm=llm,
            tools=tools,
            knowledge=knowledge,
            settings=self._settings,
        )

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def pipeline(self) -> LangGraphPipeline:
        """Escape hatch for advanced users."""
        return self._pipeline

    async def reply(self, message: str, history: Sequence[dict] | None = None) -> str:
        """Run one turn and return the final customer-visible assistant reply."""
        messages = list(history or [])
        messages.append({"role": "user", "content": message})
        state = await self._pipeline.invoke({"messages": messages})
        for entry in reversed(state.get("messages", [])):
            if entry.get("role") == "assistant":
                return str(entry.get("content") or "")
        return ""

    def stream(
        self, message: str, history: Sequence[dict] | None = None
    ) -> AsyncGenerator[dict, None]:
        """Stream one turn as pipeline updates (start/streaming/tool/done)."""
        messages = list(history or [])
        messages.append({"role": "user", "content": message})
        return self._pipeline.stream({"messages": messages})

    async def close(self) -> None:
        await self._pipeline.close()

    async def __aenter__(self) -> AgentRuntime:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

"""Embeddable runtime façade and shipped test fakes."""

from __future__ import annotations

import asyncio

from bridge_agents.runtime import AgentRuntime
from bridge_agents.testing import FakeChatModel, FakeModerator


def test_agent_runtime_returns_the_reviewed_reply() -> None:
    async def run() -> str:
        runtime = AgentRuntime(llm=FakeChatModel(reply="Hello from the runtime."), tools=[])
        try:
            return await runtime.reply("hi")
        finally:
            await runtime.close()

    assert asyncio.run(run()) == "Hello from the runtime."


def test_agent_runtime_streams_pipeline_updates() -> None:
    async def run() -> list[dict]:
        runtime = AgentRuntime(llm=FakeChatModel(reply="streamed answer"), tools=[])
        try:
            return [update async for update in runtime.stream("hi")]
        finally:
            await runtime.close()

    updates = asyncio.run(run())
    assert updates[0]["phase"] == "start"
    assert updates[-1]["phase"] == "done"
    assert "streamed answer" in updates[-1]["messages"][-1]["content"]


def test_fake_moderator_is_configurable() -> None:
    async def run(flagged: bool):
        moderator = FakeModerator(flagged=flagged)
        return await moderator.check("text")

    verdict = asyncio.run(run(True))
    assert verdict.flagged is True
    assert verdict.categories == {"test": True}

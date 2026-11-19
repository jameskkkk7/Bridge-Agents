"""Deterministic test doubles for library users.

Shipping the fakes makes it cheap to unit-test code that embeds the runtime::

    from bridge_agents.runtime import AgentRuntime
    from bridge_agents.testing import FakeChatModel, FakeModerator

    runtime = AgentRuntime(llm=FakeChatModel(reply="hello"))
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk

from bridge_agents.moderation import ModerationError, ModerationVerdict


def _is_review_call(messages: list) -> bool:
    for message in messages:
        content = getattr(message, "content", "")
        if isinstance(content, str) and "content reviewer" in content.lower():
            return True
    return False


class FakeChatModel:
    """Minimal chat model: fixed reply, fixed reviewer verdict."""

    def __init__(
        self,
        reply: str = "This is a deterministic reply.",
        review: str = '{"normal": true}',
    ):
        self.reply = reply
        self.review = review
        self.calls: list[list] = []

    async def ainvoke(self, messages, config=None, **kwargs):
        self.calls.append(list(messages))
        content = self.review if _is_review_call(list(messages)) else self.reply
        return AIMessage(content=content)

    async def astream(self, messages, config=None, **kwargs):
        self.calls.append(list(messages))
        yield AIMessageChunk(content=self.reply)

    def bind_tools(self, tools) -> FakeChatModel:
        return self


class FakeModerator:
    """Configurable moderation adapter for tests."""

    def __init__(self, *, flagged: bool = False, error: Exception | None = None) -> None:
        self.flagged = flagged
        self.error = error
        self.calls: list[str] = []

    async def check(self, text: str) -> ModerationVerdict:
        self.calls.append(text)
        if self.error is not None:
            raise self.error
        categories = {"test": True} if self.flagged else {}
        return ModerationVerdict(
            flagged=self.flagged,
            categories=categories,
            reason="test" if self.flagged else "",
        )


__all__ = ["FakeChatModel", "FakeModerator", "ModerationError", "ModerationVerdict", "Any"]

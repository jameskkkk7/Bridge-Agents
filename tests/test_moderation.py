"""Provider-backed moderation: HTTP contract and pipeline behaviour."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from bridge_agents.agent.pipeline import LangGraphPipeline
from bridge_agents.moderation import (
    ModerationError,
    ModerationVerdict,
    OpenAICompatibleModerator,
    create_moderator,
)
from langchain_core.messages import AIMessage, HumanMessage


def _run(node, state):
    return asyncio.run(node(state))


async def test_moderator_posts_to_provider_and_parses_verdict() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "flagged": True,
                        "categories": {"violence": True, "hate": False},
                    }
                ]
            },
        )

    moderator = OpenAICompatibleModerator(
        base_url="http://provider.test/v1/",
        api_key="provider-key",
        model="moderation-model",
        transport=httpx.MockTransport(handler),
    )
    verdict = await moderator.check("flagged text")

    assert str(seen["url"]) == "http://provider.test/v1/moderations"
    assert seen["auth"] == "Bearer provider-key"
    assert seen["body"] == {"model": "moderation-model", "input": "flagged text"}
    assert verdict == ModerationVerdict(
        flagged=True,
        categories={"violence": True},
        reason="violence",
    )


async def test_moderator_reports_provider_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="provider down")

    moderator = OpenAICompatibleModerator(
        base_url="http://provider.test/v1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModerationError):
        await moderator.check("hello")


async def test_moderator_skips_empty_text_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("empty moderation text must not hit the network")

    moderator = OpenAICompatibleModerator(
        base_url="http://provider.test/v1",
        transport=httpx.MockTransport(handler),
    )
    verdict = await moderator.check("   ")
    assert verdict.flagged is False


class _FakeModerator:
    def __init__(self, *, flagged: bool = False, error: Exception | None = None) -> None:
        self.flagged = flagged
        self.error = error
        self.calls: list[str] = []

    async def check(self, text: str) -> ModerationVerdict:
        self.calls.append(text)
        if self.error is not None:
            raise self.error
        return ModerationVerdict(
            flagged=self.flagged,
            categories={"violence": True} if self.flagged else {},
            reason="violence" if self.flagged else "",
        )


def _pipeline(moderator: _FakeModerator | None = None) -> LangGraphPipeline:
    return LangGraphPipeline(tools=[], moderator=moderator)


def test_sanitize_provider_checks_only_the_latest_draft() -> None:
    moderator = _FakeModerator(flagged=True)
    pipeline = _pipeline(moderator)
    node = pipeline._make_sanitize_node(
        {
            "banned_words": ["damn"],
            "replacement": "***",
            "provider_enabled": True,
            "provider_fallback": "BLOCKED",
        }
    )
    messages = [
        HumanMessage(content="hi", id="h1"),
        AIMessage(content="damn old reply", id="a1"),
        AIMessage(content="latest draft", id="a2"),
    ]
    update = _run(node, {"messages": messages})
    assert moderator.calls == ["latest draft"]
    by_id = {message.id: message.content for message in update["messages"]}
    assert by_id == {"a1": "*** old reply", "a2": "BLOCKED"}


def test_sanitize_provider_failure_can_fail_open_or_closed() -> None:
    error = ModerationError("provider down")
    messages = [AIMessage(content="reply", id="a1")]

    open_pipeline = _pipeline(_FakeModerator(error=error))
    open_node = open_pipeline._make_sanitize_node(
        {"provider_enabled": True, "provider_fallback": "BLOCKED"}
    )
    assert _run(open_node, {"messages": messages}) == {}

    closed_pipeline = _pipeline(_FakeModerator(error=error))
    closed_node = closed_pipeline._make_sanitize_node(
        {
            "provider_enabled": True,
            "provider_fallback": "BLOCKED",
            "provider_fail_open": False,
        }
    )
    closed_update = _run(closed_node, {"messages": messages})
    assert closed_update["messages"][0].content == "BLOCKED"


def test_sanitize_provider_is_off_by_default() -> None:
    moderator = _FakeModerator(flagged=True)
    pipeline = _pipeline(moderator)
    node = pipeline._make_sanitize_node({"banned_words": ["damn"], "replacement": "***"})
    update = _run(
        node,
        {"messages": [AIMessage(content="damn reply", id="a1")]},
    )
    assert moderator.calls == []
    assert update["messages"][0].content == "*** reply"


async def test_moderator_works_against_the_bundled_mock_endpoint() -> None:
    from mock.main import app as mock_app

    moderator = OpenAICompatibleModerator(
        base_url="http://mock/v1",
        transport=httpx.ASGITransport(app=mock_app),
    )
    flagged = await moderator.check("please [[moderation]] this")
    safe = await moderator.check("friendly hello")
    assert flagged.flagged is True
    assert flagged.categories == {"violence": True}
    assert safe.flagged is False


def test_sanitize_node_uses_the_mock_provider_end_to_end() -> None:
    from mock.main import app as mock_app

    moderator = OpenAICompatibleModerator(
        base_url="http://mock/v1",
        transport=httpx.ASGITransport(app=mock_app),
    )
    pipeline = LangGraphPipeline(tools=[], moderator=moderator)
    node = pipeline._make_sanitize_node(
        {
            "provider_enabled": True,
            "provider_fallback": "BLOCKED BY PROVIDER",
        }
    )
    update = _run(
        node,
        {"messages": [AIMessage(content="[[moderation]] draft", id="a1")]},
    )
    assert update["messages"][0].content == "BLOCKED BY PROVIDER"


async def test_azure_adapter_reads_severities_and_threshold() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("ocp-apim-subscription-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "categoriesAnalysis": [
                    {"category": "Hate", "severity": 2},
                    {"category": "Violence", "severity": 4},
                    {"category": "Sexual", "severity": 0},
                ]
            },
        )

    moderator = create_moderator(
        "azure",
        base_url="https://resource.cognitiveservices.azure.com",
        api_key="azure-key",
        api_version="2024-09-01",
        severity_threshold=2,
        transport=httpx.MockTransport(handler),
    )
    verdict = await moderator.check("bad text")

    assert str(seen["url"]).startswith(
        "https://resource.cognitiveservices.azure.com/contentsafety/text:analyze"
    )
    assert "api-version=2024-09-01" in str(seen["url"])
    assert seen["key"] == "azure-key"
    assert seen["body"]["categories"] == ["Hate", "Sexual", "SelfHarm", "Violence"]
    assert verdict.flagged is True
    assert verdict.categories == {"Hate": True, "Violence": True}
    assert "Violence=4" in verdict.reason


async def test_azure_adapter_below_threshold_is_safe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "categoriesAnalysis": [
                    {"category": "Hate", "severity": 0},
                    {"category": "Violence", "severity": 1},
                ]
            },
        )

    moderator = create_moderator(
        "azure",
        base_url="https://resource.cognitiveservices.azure.com",
        api_key="azure-key",
        severity_threshold=2,
        transport=httpx.MockTransport(handler),
    )
    verdict = await moderator.check("mild text")
    assert verdict.flagged is False


async def test_perspective_adapter_reads_toxicity_score() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["key"] = request.url.params.get("key")
        return httpx.Response(
            200,
            json={
                "attributeScores": {
                    "TOXICITY": {"summaryScore": {"value": 0.91, "type": "PROBABILITY"}}
                }
            },
        )

    moderator = create_moderator(
        "perspective",
        base_url="https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze",
        api_key="perspective-key",
        threshold=0.7,
        language="en",
        transport=httpx.MockTransport(handler),
    )
    verdict = await moderator.check("toxic text")

    assert seen["key"] == "perspective-key"
    assert seen["body"]["comment"] == {"text": "toxic text"}
    assert seen["body"]["languages"] == ["en"]
    assert verdict.flagged is True
    assert verdict.categories == {"TOXICITY": True}


async def test_create_moderator_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError):
        create_moderator("not-a-provider")

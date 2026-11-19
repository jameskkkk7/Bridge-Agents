"""Provider-backed moderation: HTTP contract and pipeline behaviour."""

from __future__ import annotations

import asyncio
import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest
from bridge_agents.agent.factory import validate_graph_config
from bridge_agents.agent.pipeline import LangGraphPipeline
from bridge_agents.config import Settings
from bridge_agents.moderation import (
    AliyunTextModerationModerator,
    ModerationError,
    ModerationVerdict,
    OpenAICompatibleModerator,
    TencentTextModerationModerator,
    aliyun_rpc_signature,
    create_moderator,
    provider_credentials_error,
    redact_secret_urls,
    resolve_provider_base_url,
    tencent_tc3_headers,
    validate_sanitize_provider_config,
)
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage


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


async def test_aliyun_signature_matches_official_example() -> None:
    params = {
        "Timestamp": "2016-02-23T12:46:24Z",
        "Format": "XML",
        "AccessKeyId": "testid",
        "Action": "DescribeRegions",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": "3ee8c1b8-83d3-44af-a94f-4e0ad82fd6cf",
        "Version": "2014-05-26",
        "SignatureVersion": "1.0",
    }
    assert aliyun_rpc_signature("GET", params, "testsecret") == "OLeaidS1JvxuMvnyHOwuJ+uX5qY="


async def test_aliyun_adapter_flags_labels_from_provider() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["form"] = parse_qs(request.content.decode())
        return httpx.Response(
            200,
            json={
                "Code": 200,
                "Message": "OK",
                "Data": {"labels": "porn,ad", "reason": "{}"},
            },
        )

    moderator = AliyunTextModerationModerator(
        endpoint="https://green-cip.cn-shanghai.aliyuncs.com",
        access_key_id="aliyun-id",
        access_key_secret="aliyun-secret",
        service="comment_detection",
        timestamp="2024-01-01T00:00:00Z",
        nonce="test-nonce",
        transport=httpx.MockTransport(handler),
    )
    verdict = await moderator.check("flagged text")

    assert verdict.flagged is True
    assert verdict.categories == {"porn": True, "ad": True}
    form = captured["form"]
    assert form["Action"] == ["TextModeration"]
    assert form["Version"] == ["2022-03-02"]
    assert form["AccessKeyId"] == ["aliyun-id"]
    assert json.loads(form["ServiceParameters"][0]) == {"content": "flagged text"}
    assert form["Signature"][0]


def test_tencent_tc3_headers_match_official_example() -> None:
    payload = (
        b'{"Limit": 1, "Filters": [{"Values": ["\\u672a\\u547d\\u540d"], "Name": "instance-name"}]}'
    )
    headers = tencent_tc3_headers(
        secret_id="AKIDz8krbsJ5yKBZQpn74WFkmLPx3EXAMPLE",
        secret_key="Gu5t9xGARNpq86cd98joQYCN3EXAMPLE",
        host="cvm.tencentcloudapi.com",
        service="cvm",
        action="DescribeInstances",
        version="2017-03-12",
        region="ap-guangzhou",
        payload=payload,
        timestamp=1551113065,
    )
    expected = (
        "TC3-HMAC-SHA256 Credential=AKIDz8krbsJ5yKBZQpn74WFkmLPx3EXAMPLE/"
        "2019-02-25/cvm/tc3_request, SignedHeaders=content-type;host, "
        "Signature=72e494ea809ad7a8c8f7a4507b9bddcbaa8e581f516e8da2f66e2c5a96525168"
    )
    assert headers["Authorization"] == expected


async def test_tencent_adapter_flags_moderation_suggestion() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "Response": {
                    "Suggestion": "Block",
                    "Label": "Porn",
                    "Score": 85,
                    "RequestId": "req-1",
                }
            },
        )

    moderator = TencentTextModerationModerator(
        endpoint="https://tms.tencentcloudapi.com",
        secret_id="secret-id",
        secret_key="secret-key",
        region="ap-guangzhou",
        transport=httpx.MockTransport(handler),
        timestamp=1700000000,
    )
    verdict = await moderator.check("flagged text")

    assert verdict.flagged is True
    assert verdict.categories == {"Porn": True}
    assert captured["body"]["Content"] == "ZmxhZ2dlZCB0ZXh0"
    assert "TC3-HMAC-SHA256 Credential=secret-id/" in captured["authorization"]


async def test_tencent_adapter_reports_api_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "Response": {
                    "Error": {"Code": "AuthFailure.SignatureFailure", "Message": "bad sig"}
                }
            },
        )

    moderator = TencentTextModerationModerator(
        endpoint="https://tms.tencentcloudapi.com",
        secret_id="secret-id",
        secret_key="secret-key",
        transport=httpx.MockTransport(handler),
        timestamp=1700000000,
    )
    with pytest.raises(ModerationError):
        await moderator.check("hello")


# --- hardening: defensive parsing, redaction, chunking, gating ---------------


class _RaisingModerator:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls: list[str] = []

    async def check(self, text: str) -> ModerationVerdict:
        self.calls.append(text)
        raise self.error


def _sanitize_graph(sanitize_config: dict) -> dict:
    return {
        "nodes": [
            {"id": "__start__", "type": "start", "config": {}},
            {"id": "system_node", "type": "system", "config": {"system_prompt": "Be nice."}},
            {"id": "agent_node", "type": "agent", "config": {}},
            {"id": "sanitize_node", "type": "sanitize", "config": sanitize_config},
            {"id": "__end__", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "__start__", "target": "system_node"},
            {"source": "system_node", "target": "agent_node"},
            {"source": "agent_node", "target": "sanitize_node"},
            {"source": "sanitize_node", "target": "__end__"},
        ],
    }


def _collect(generator) -> list[dict]:
    async def _gather() -> list[dict]:
        return [update async for update in generator]

    return asyncio.run(_gather())


def test_secret_query_parameters_are_redacted() -> None:
    redacted = redact_secret_urls(
        "POST https://x.test/y?key=SECRET-VALUE&other=1&api_key=OTHER-SECRET failed"
    )
    assert "SECRET-VALUE" not in redacted
    assert "OTHER-SECRET" not in redacted
    assert "key=***" in redacted


async def test_openai_malformed_categories_raise_moderation_error() -> None:
    moderator = OpenAICompatibleModerator(
        base_url="http://provider.test/v1",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"results": [{"flagged": False, "categories": ["violence"]}]}
            )
        ),
    )
    with pytest.raises(ModerationError):
        await moderator.check("hello")


async def test_openai_invalid_endpoint_is_rejected_before_any_request() -> None:
    with pytest.raises(ValueError):
        OpenAICompatibleModerator(base_url="http://provider.test:badport/v1")


async def test_perspective_missing_verdict_raises_moderation_error() -> None:
    moderator = create_moderator(
        "perspective",
        base_url="https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze",
        api_key="perspective-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"attributeScores": {"TOXICITY": {}}})
        ),
    )
    with pytest.raises(ModerationError):
        await moderator.check("hello")


async def test_tencent_missing_verdict_raises_moderation_error() -> None:
    moderator = TencentTextModerationModerator(
        secret_id="secret-id",
        secret_key="secret-key",
        timestamp=1700000000,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"Response": {"RequestId": "r"}})
        ),
    )
    with pytest.raises(ModerationError):
        await moderator.check("hello")


async def test_aliyun_missing_data_raises_moderation_error() -> None:
    moderator = AliyunTextModerationModerator(
        endpoint="https://green-cip.cn-shanghai.aliyuncs.com",
        access_key_id="aliyun-id",
        access_key_secret="aliyun-secret",
        timestamp="2024-01-01T00:00:00Z",
        nonce="test-nonce",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"Code": 200, "Message": "OK"})
        ),
    )
    with pytest.raises(ModerationError):
        await moderator.check("hello")


async def test_aliyun_splits_long_replies_into_600_char_requests() -> None:
    contents: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        content = json.loads(form["ServiceParameters"][0])["content"]
        contents.append(content)
        labels = "profanity" if "bad" in content else ""
        return httpx.Response(200, json={"Code": 200, "Data": {"labels": labels}})

    moderator = AliyunTextModerationModerator(
        endpoint="https://green-cip.cn-shanghai.aliyuncs.com",
        access_key_id="aliyun-id",
        access_key_secret="aliyun-secret",
        timestamp="2024-01-01T00:00:00Z",
        transport=httpx.MockTransport(handler),
    )
    text = "a" * 500 + " bad " + "b" * 500
    verdict = await moderator.check(text)

    assert len(contents) >= 2
    assert all(len(content) <= 600 for content in contents)
    assert "".join(contents) == text
    assert verdict.flagged is True


async def test_tencent_splits_long_replies_into_10000_char_requests() -> None:
    decoded: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        decoded.append(base64.b64decode(body["Content"]).decode("utf-8"))
        return httpx.Response(200, json={"Response": {"Suggestion": "Pass", "Label": "Normal"}})

    moderator = TencentTextModerationModerator(
        secret_id="secret-id",
        secret_key="secret-key",
        timestamp=1700000000,
        transport=httpx.MockTransport(handler),
    )
    text = "x" * 10_001
    verdict = await moderator.check(text)

    assert len(decoded) == 2
    assert "".join(decoded) == text
    assert verdict.flagged is False


def test_sanitize_node_applies_policy_to_unexpected_provider_exceptions() -> None:
    messages = [AIMessage(content="reply", id="a1")]

    open_pipeline = _pipeline(_RaisingModerator(AttributeError("boom")))
    open_node = open_pipeline._make_sanitize_node(
        {"provider_enabled": True, "provider_fallback": "BLOCKED"}
    )
    assert _run(open_node, {"messages": messages}) == {}

    closed_pipeline = _pipeline(_RaisingModerator(ValueError("boom")))
    closed_node = closed_pipeline._make_sanitize_node(
        {
            "provider_enabled": True,
            "provider_fallback": "BLOCKED",
            "provider_fail_open": False,
        }
    )
    update = _run(closed_node, {"messages": messages})
    assert update["messages"][0].content == "BLOCKED"


def test_enabled_provider_without_credentials_is_not_silently_skipped() -> None:
    settings = Settings(
        moderation_provider="azure",
        moderation_azure_endpoint="",
        moderation_azure_key="",
    )
    pipeline = LangGraphPipeline(tools=[], settings=settings)
    messages = [AIMessage(content="reply", id="a1")]

    open_node = pipeline._make_sanitize_node(
        {"provider_enabled": True, "provider_fail_open": True, "provider_fallback": "BLOCKED"}
    )
    assert _run(open_node, {"messages": messages}) == {}

    closed_node = pipeline._make_sanitize_node(
        {
            "provider_enabled": True,
            "provider_fail_open": False,
            "provider_fallback": "BLOCKED",
        }
    )
    update = _run(closed_node, {"messages": messages})
    assert update["messages"][0].content == "BLOCKED"


def test_sanitize_checks_only_the_last_assistant_message_without_ids() -> None:
    moderator = _FakeModerator(flagged=True)
    node = _pipeline(moderator)._make_sanitize_node(
        {"provider_enabled": True, "provider_fallback": "BLOCKED"}
    )
    messages = [AIMessage(content="old reply"), AIMessage(content="latest draft")]
    _run(node, {"messages": messages})
    assert moderator.calls == ["latest draft"]


def test_validate_sanitize_provider_config_rejects_unusable_values() -> None:
    assert validate_sanitize_provider_config({"provider_enabled": "false"}) is None
    assert "unknown" in (
        validate_sanitize_provider_config({"provider_enabled": True, "provider": "not-a-provider"})
        or ""
    )
    assert "between" in (
        validate_sanitize_provider_config({"provider_enabled": True, "provider_threshold": 0}) or ""
    )
    assert "between" in (
        validate_sanitize_provider_config({"provider_enabled": True, "provider_severity": 0}) or ""
    )
    assert "provider_timeout" in (
        validate_sanitize_provider_config({"provider_enabled": True, "provider_timeout": 600}) or ""
    )
    assert "URL" in (
        validate_sanitize_provider_config(
            {"provider_enabled": True, "provider_base_url": "http://host:badport/v1"}
        )
        or ""
    )
    assert (
        validate_sanitize_provider_config({"provider_enabled": True, "provider_fail_open": "false"})
        is None
    )


def test_validate_graph_config_rejects_unusable_provider() -> None:
    config = _sanitize_graph({"provider_enabled": True, "provider": "not-a-provider"})
    error = validate_graph_config(config, settings=Settings())
    assert error is not None
    assert "unknown moderation provider" in error

    fail_closed = _sanitize_graph(
        {
            "provider_enabled": True,
            "provider": "azure",
            "provider_fail_open": False,
            "provider_base_url": "https://resource.cognitiveservices.azure.com",
        }
    )
    settings = Settings(moderation_azure_key="")
    error = validate_graph_config(fail_closed, settings=settings)
    assert error is not None
    assert "MODERATION_AZURE_KEY" in error


def test_stream_gate_holds_tokens_until_provider_sanitize_ran() -> None:
    class _SafeModerator:
        async def check(self, text: str) -> ModerationVerdict:
            return ModerationVerdict(flagged=False)

    class _FakeCompiled:
        def __init__(self, events: list[tuple[str, object]]) -> None:
            self.events = events

        async def astream(self, graph_state, config=None, stream_mode=None):
            for event in self.events:
                yield event

    config = _sanitize_graph({"provider_enabled": True, "provider_fallback": "BLOCKED"})
    pipeline = LangGraphPipeline(config, tools=[], moderator=_SafeModerator())
    pipeline._compiled = _FakeCompiled(
        [
            (
                "messages",
                (
                    AIMessageChunk(content="unsafe draft", id="a1"),
                    {"langgraph_node": "agent_node"},
                ),
            ),
            ("updates", {"agent_node": {"messages": [AIMessage(content="unsafe draft", id="a1")]}}),
            ("updates", {"sanitize_node": {"messages": [AIMessage(content="BLOCKED", id="a1")]}}),
        ]
    )
    updates = _collect(pipeline.stream({"messages": [{"role": "user", "content": "hi"}]}))
    streamed = " ".join(
        update["messages"][-1]["content"]
        for update in updates
        if update.get("phase") == "streaming" and update.get("messages")
    )
    assert "unsafe" not in streamed
    assert updates[-1]["phase"] == "done"
    assert updates[-1]["messages"][-1]["content"] == "BLOCKED"


def test_validate_sanitize_provider_config_rejects_embedded_credentials() -> None:
    with_query = validate_sanitize_provider_config(
        {"provider_enabled": True, "provider_base_url": "https://host/v1?key=secret"}
    )
    assert with_query is not None and "query" in with_query
    with_userinfo = validate_sanitize_provider_config(
        {"provider_enabled": True, "provider_base_url": "https://user:pass@host/v1"}
    )
    assert with_userinfo is not None and "credentials" in with_userinfo


def test_provider_allowlist_rejects_unlisted_hosts() -> None:
    settings = Settings(moderation_allowed_hosts="allowed.example")
    with pytest.raises(ValueError, match="MODERATION_ALLOWED_HOSTS"):
        resolve_provider_base_url(
            "openai", {"provider_base_url": "https://evil.example/v1"}, settings
        )
    resolved = resolve_provider_base_url(
        "openai", {"provider_base_url": "https://allowed.example/v1"}, settings
    )
    assert resolved == "https://allowed.example/v1"


def test_provider_keys_are_not_reused_across_vendors() -> None:
    settings = Settings(moderation_api_key="generic-key", moderation_azure_key="")
    assert provider_credentials_error("azure", settings) == (
        "MODERATION_AZURE_KEY is not configured"
    )
    assert provider_credentials_error("perspective", settings) == (
        "MODERATION_PERSPECTIVE_KEY is not configured"
    )


def test_stream_gate_works_through_a_compiled_graph() -> None:
    class _StreamingModel:
        async def astream(self, messages, config=None):
            yield AIMessageChunk(content="unsafe refund promise ")
            yield AIMessageChunk(content="guaranteed refund")

    class _FlaggedModerator:
        async def check(self, text: str) -> ModerationVerdict:
            return ModerationVerdict(flagged=True, categories={"violence": True}, reason="violence")

    config = _sanitize_graph({"provider_enabled": True, "provider_fallback": "BLOCKED BY PROVIDER"})
    pipeline = LangGraphPipeline(
        config, tools=[], llm=_StreamingModel(), moderator=_FlaggedModerator()
    )
    updates = _collect(pipeline.stream({"messages": [{"role": "user", "content": "refund?"}]}))
    visible = " ".join(
        update["messages"][-1]["content"] for update in updates if update.get("messages")
    )
    assert "guaranteed" not in visible
    assert updates[-1]["messages"][-1]["content"] == "BLOCKED BY PROVIDER"


def _graph_with_parallel_gates(sanitize_config: dict) -> dict:
    return {
        "nodes": [
            {"id": "__start__", "type": "start", "config": {}},
            {"id": "system_node", "type": "system", "config": {"system_prompt": "Be nice."}},
            {"id": "agent_node", "type": "agent", "config": {}},
            {"id": "sanitize_node", "type": "sanitize", "config": sanitize_config},
            {"id": "review_node", "type": "review", "config": {"on_block": "fallback"}},
            {"id": "__end__", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "__start__", "target": "system_node"},
            {"source": "system_node", "target": "agent_node"},
            {"source": "agent_node", "target": "sanitize_node"},
            {"source": "agent_node", "target": "review_node"},
            {"source": "sanitize_node", "target": "__end__"},
            {"source": "review_node", "target": "__end__", "condition": "pass"},
        ],
    }


def test_stream_gate_waits_for_parallel_gate_nodes() -> None:
    class _SafeModerator:
        async def check(self, text: str) -> ModerationVerdict:
            return ModerationVerdict(flagged=False)

    class _FakeCompiled:
        def __init__(self, events: list[tuple[str, object]]) -> None:
            self.events = events

        async def astream(self, graph_state, config=None, stream_mode=None):
            for event in self.events:
                yield event

    config = _graph_with_parallel_gates({"provider_enabled": True, "provider_fallback": "BLOCKED"})
    pipeline = LangGraphPipeline(config, tools=[], moderator=_SafeModerator())
    raw = "unsafe parallel draft"
    pipeline._compiled = _FakeCompiled(
        [
            ("updates", {"agent_node": {"messages": [AIMessage(content=raw, id="a1")]}}),
            ("updates", {"sanitize_node": {"messages": [AIMessage(content=raw, id="a1")]}}),
            (
                "updates",
                {
                    "review_node": {
                        "messages": [
                            AIMessage(
                                id="a1",
                                content=raw,
                                response_metadata={"review_blocked": True},
                            )
                        ]
                    }
                },
            ),
            ("updates", {"agent_node": {"messages": [AIMessage(content="safe reply", id="a2")]}}),
            ("updates", {"review_node": {"messages": []}}),
        ]
    )
    updates = _collect(pipeline.stream({"messages": [{"role": "user", "content": "hi"}]}))
    visible = " ".join(
        update["messages"][-1]["content"]
        for update in updates
        if update.get("messages") and update.get("phase") == "streaming"
    )
    assert raw not in visible
    assert updates[-1]["messages"][-1]["content"] == "safe reply"


async def test_aliyun_refuses_pathological_chunk_counts() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(1)
        return httpx.Response(200, json={"Code": 200, "Data": {"labels": ""}})

    moderator = AliyunTextModerationModerator(
        endpoint="https://green-cip.cn-shanghai.aliyuncs.com",
        access_key_id="aliyun-id",
        access_key_secret="aliyun-secret",
        timestamp="2024-01-01T00:00:00Z",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModerationError):
        await moderator.check("x" * (600 * 70))
    assert calls == []


async def test_openai_numeric_category_values_are_accepted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [{"flagged": False, "categories": {"hate": 0.0, "violence": 0.2}}]},
        )

    moderator = OpenAICompatibleModerator(
        base_url="http://provider.test/v1", transport=httpx.MockTransport(handler)
    )
    verdict = await moderator.check("hello")
    assert verdict.flagged is False
    assert verdict.categories == {"violence": True}


def test_validate_sanitize_provider_config_handles_invalid_ipv6_and_allowlist_normalisation() -> (
    None
):
    invalid_ipv6 = validate_sanitize_provider_config(
        {"provider_enabled": True, "provider_base_url": "http://[::1"}
    )
    assert invalid_ipv6 is not None

    settings = Settings(moderation_allowed_hosts="allowed.example.,allowed.example:8443,[::1]")
    assert (
        resolve_provider_base_url(
            "openai", {"provider_base_url": "https://ALLOWED.example/v1"}, settings
        )
        == "https://ALLOWED.example/v1"
    )
    assert (
        resolve_provider_base_url(
            "openai", {"provider_base_url": "https://allowed.example:8443/v1"}, settings
        )
        == "https://allowed.example:8443/v1"
    )


def _graph_with_conditional_gates() -> dict:
    return {
        "nodes": [
            {"id": "__start__", "type": "start", "config": {}},
            {"id": "system_node", "type": "system", "config": {"system_prompt": "Be nice."}},
            {"id": "agent_node", "type": "agent", "config": {}},
            {"id": "review_node", "type": "review", "config": {"on_block": "fallback"}},
            {
                "id": "sanitize_node",
                "type": "sanitize",
                "config": {"provider_enabled": True, "provider_fallback": "BLOCKED"},
            },
            {"id": "__end__", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "__start__", "target": "system_node"},
            {"source": "system_node", "target": "agent_node"},
            {"source": "agent_node", "target": "review_node", "condition": "respond"},
            {"source": "agent_node", "target": "sanitize_node", "condition": "tool_call"},
            {"source": "review_node", "target": "__end__", "condition": "pass"},
            {"source": "sanitize_node", "target": "__end__"},
        ],
    }


def test_stream_gate_ignores_gates_on_unchosen_conditional_branches() -> None:
    class _SafeModerator:
        async def check(self, text: str) -> ModerationVerdict:
            return ModerationVerdict(flagged=False)

    class _FakeCompiled:
        def __init__(self, events: list[tuple[str, object]]) -> None:
            self.events = events

        async def astream(self, graph_state, config=None, stream_mode=None):
            for event in self.events:
                yield event

    config = _graph_with_conditional_gates()
    pipeline = LangGraphPipeline(config, tools=[], moderator=_SafeModerator())
    pipeline._compiled = _FakeCompiled(
        [
            ("updates", {"agent_node": {"messages": [AIMessage(content="safe draft", id="a1")]}}),
            ("updates", {"review_node": {"messages": []}}),
        ]
    )
    updates = _collect(pipeline.stream({"messages": [{"role": "user", "content": "hi"}]}))
    streaming = [update for update in updates if update.get("phase") == "streaming"]
    assert len(streaming) == 1
    assert streaming[0]["messages"][-1]["content"] == "safe draft"


async def test_chunked_checks_allow_more_than_one_request_timeout() -> None:
    calls: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1.0)
        await asyncio.sleep(0.3)
        return httpx.Response(200, json={"Code": 200, "Data": {"labels": ""}})

    moderator = AliyunTextModerationModerator(
        endpoint="https://green-cip.cn-shanghai.aliyuncs.com",
        access_key_id="aliyun-id",
        access_key_secret="aliyun-secret",
        timeout=0.5,
        timestamp="2024-01-01T00:00:00Z",
        transport=httpx.MockTransport(handler),
    )
    text = "a" * 500 + " " + "b" * 500 + " " + "c" * 500
    verdict = await moderator.check(text)
    assert verdict.flagged is False
    assert len(calls) >= 3


async def test_openai_nan_category_raises_moderation_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [{"flagged": False, "categories": {"hate": float("nan")}}]},
        )

    moderator = OpenAICompatibleModerator(
        base_url="http://provider.test/v1", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ModerationError):
        await moderator.check("hello")

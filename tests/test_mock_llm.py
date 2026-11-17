"""Mock model protocol: the four shapes the demo relies on."""

from __future__ import annotations

import json

import httpx
import pytest

from mock.main import (
    BLOCKED_SEGMENTS,
    GUARANTEE_SEGMENTS,
    NORMAL_SEGMENTS,
    REVIEW_MARKER,
    app,
)


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://mock") as http_client:
        yield http_client


async def _chat(client, messages: list[dict], stream: bool = False):
    response = await client.post(
        "/v1/chat/completions",
        json={"model": "mock-model", "messages": messages, "stream": stream},
    )
    assert response.status_code == 200, response.text
    return response


def _sse_text(body: str) -> str:
    parts: list[str] = []
    tool_names: list[str] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :]
        if payload == "[DONE]":
            continue
        chunk = json.loads(payload)
        for choice in chunk.get("choices", []):
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                parts.append(content)
            for call in delta.get("tool_calls") or []:
                name = (call.get("function") or {}).get("name")
                if name:
                    tool_names.append(name)
    return "".join(parts) if not tool_names else "|".join(tool_names)


async def test_health_and_model_listing(client) -> None:
    assert (await client.get("/health")).json() == {"status": "ok"}
    models = (await client.get("/v1/models")).json()
    assert models["data"][0]["id"] == "mock-model"


async def test_normal_completion_and_streaming_match(client) -> None:
    messages = [{"role": "user", "content": "hello"}]
    plain = (await _chat(client, messages)).json()
    expected = "".join(NORMAL_SEGMENTS)
    assert plain["choices"][0]["message"]["content"] == expected

    streamed = await _chat(client, messages, stream=True)
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert _sse_text(streamed.text) == expected
    assert streamed.text.rstrip().endswith("data: [DONE]")


async def test_guarantee_reply_promises_a_refund(client) -> None:
    response = await _chat(client, [{"role": "user", "content": "Can you guarantee a refund?"}])
    content = response.json()["choices"][0]["message"]["content"]
    assert content == "".join(GUARANTEE_SEGMENTS)
    assert "we guarantee" in content


async def test_explicit_block_marker_is_echoed(client) -> None:
    response = await _chat(client, [{"role": "user", "content": "please [[blocked]]"}])
    content = response.json()["choices"][0]["message"]["content"]
    assert content == "".join(BLOCKED_SEGMENTS)
    assert "[[blocked]]" in content


async def test_reviewer_verdicts(client) -> None:
    def review(draft: str) -> dict:
        return [
            {"role": "system", "content": f"{REVIEW_MARKER}. Reply with JSON."},
            {"role": "user", "content": draft},
        ]

    safe = (await _chat(client, review("Refunds follow the policy."))).json()
    assert json.loads(safe["choices"][0]["message"]["content"])["normal"] is True

    blocked = (await _chat(client, review("Yes, we guarantee a refund."))).json()
    verdict = json.loads(blocked["choices"][0]["message"]["content"])
    assert verdict["normal"] is False
    assert "refund" in verdict["reason"].lower()

    explicit = (await _chat(client, review("draft [[blocked]]"))).json()
    assert json.loads(explicit["choices"][0]["message"]["content"])["normal"] is False


async def test_tool_call_flow(client) -> None:
    first = await _chat(client, [{"role": "user", "content": "[[tool]] what time is it?"}])
    message = first.json()["choices"][0]["message"]
    assert message["tool_calls"][0]["function"]["name"] == "get_current_time"

    follow_up = [
        {"role": "user", "content": "[[tool]] what time is it?"},
        {"role": "assistant", "content": None, "tool_calls": message["tool_calls"]},
        {"role": "tool", "content": "2026-01-01 00:00:00 UTC", "tool_call_id": "call_mock_tool_1"},
    ]
    second = await _chat(client, follow_up)
    content = second.json()["choices"][0]["message"]["content"]
    assert content.startswith("The tool returned:")
    assert "2026-01-01" in content


async def test_tool_call_is_also_streamable(client) -> None:
    response = await _chat(client, [{"role": "user", "content": "[[tool]] time?"}], stream=True)
    assert _sse_text(response.text) == "get_current_time"


async def test_embeddings_are_deterministic(client) -> None:
    payload = {"model": "mock-embedding", "input": ["activate widget", "refund policy"]}
    first = await client.post("/v1/embeddings", json=payload)
    second = await client.post("/v1/embeddings", json=payload)
    assert first.status_code == 200
    assert first.json() == second.json()
    data = first.json()["data"]
    assert [item["index"] for item in data] == [0, 1]
    vector = data[0]["embedding"]
    assert len(vector) == 256
    norm = sum(value * value for value in vector) ** 0.5
    assert abs(norm - 1.0) < 1e-3


async def test_embeddings_accept_a_single_string(client) -> None:
    response = await client.post("/v1/embeddings", json={"input": "activate widget"})
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


async def test_knowledge_context_produces_a_cited_answer(client) -> None:
    messages = [
        {
            "role": "system",
            "content": (
                "Retrieved knowledge for this question. Cite sources like [1].\n\n"
                "[1] Widget Pro — Activation\n"
                "Activate Widget Pro from Settings → Billing → Activate and confirm "
                "the licence key."
            ),
        },
        {"role": "user", "content": "How do I activate Widget Pro?"},
    ]
    response = await _chat(client, messages)
    content = response.json()["choices"][0]["message"]["content"]
    assert "According to the documentation (Widget Pro — Activation)" in content
    assert "[1]" in content
    assert "Settings" in content


async def test_guarantee_scenario_wins_over_knowledge_context(client) -> None:
    messages = [
        {
            "role": "system",
            "content": (
                "Retrieved knowledge for this question.\n\n[1] Refunds\nRefunds follow policy."
            ),
        },
        {"role": "user", "content": "Can you guarantee a refund?"},
    ]
    response = await _chat(client, messages)
    assert response.json()["choices"][0]["message"]["content"] == "".join(GUARANTEE_SEGMENTS)

"""Deterministic OpenAI-compatible mock model used by the demo.

The service speaks the shapes the runtime needs:

* ``POST /v1/chat/completions`` with ``stream`` false or true (SSE);
* ``POST /v1/embeddings`` with deterministic hashed vectors, so the
  OpenAI-embedding retrieval path can be exercised without a real provider;
* ordinary replies, tool-call replies, review verdicts and knowledge-grounded
  replies.

Behaviour is fully deterministic so screenshots and tests are reproducible.
Five scenarios are recognised from the request:

* a review request (system prompt contains the reviewer marker) answers with a
  JSON verdict and blocks drafts that contain ``guarantee`` or ``[[blocked]]``;
* a user message containing ``[[tool]]`` first asks for a ``get_current_time``
  tool call and then summarises the tool result;
* a user message containing ``guarantee`` produces a reply that promises a
  refund, which the review gate then rejects;
* a request carrying retrieved knowledge answers with a citation taken from the
  first retrieved passage;
* everything else produces a short canned answer in two or three segments.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse

from mock.grounding import (
    EMBEDDING_DIMENSION,
    embedding_vector,
    knowledge_segments,
)

REVIEW_MARKER = "You are a content reviewer"
TOOL_NAME = "get_current_time"

DELAY_SECONDS = float(os.getenv("MOCK_DELAY_MS", "25")) / 1000.0

NORMAL_SEGMENTS = [
    "Thanks for reaching out. ",
    "I can help with orders, activation and refunds. ",
    "Refund requests follow the 14-day policy.",
]
GUARANTEE_SEGMENTS = [
    "Yes — ",
    "we guarantee ",
    "a full refund for every order.",
]
BLOCKED_SEGMENTS = [
    "This draft contains the explicit trigger. ",
    "[[blocked]] ",
]

app = FastAPI(title="Bridge-Agents mock model", version="0.1.0")


def _content_text(content: Any) -> str:
    """Flatten OpenAI-style message content (string or multi-part) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts)
    return ""


def _last_message(messages: list[dict], role: str) -> str:
    for message in reversed(messages):
        if message.get("role") == role:
            return _content_text(message.get("content"))
    return ""


def _has_tool_result(messages: list[dict]) -> str | None:
    for message in reversed(messages):
        if message.get("role") == "tool":
            return _content_text(message.get("content"))
    return None


def _is_review_request(messages: list[dict]) -> bool:
    return any(
        message.get("role") == "system" and REVIEW_MARKER in _content_text(message.get("content"))
        for message in messages
    )


def _completion(model: str, content: str) -> dict:
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _tool_call_completion(model: str) -> dict:
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_mock_tool_1",
                            "type": "function",
                            "function": {"name": TOOL_NAME, "arguments": "{}"},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _chunk(model: str, delta: dict, finish_reason: str | None = None) -> str:
    payload = {
        "id": "chatcmpl-mock",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload)}\n\n"


async def _stream_text(model: str, segments: list[str]) -> AsyncIterator[str]:
    yield _chunk(model, {"role": "assistant", "content": ""})
    for segment in segments:
        if DELAY_SECONDS:
            await asyncio.sleep(DELAY_SECONDS)
        yield _chunk(model, {"content": segment})
    yield _chunk(model, {}, "stop")
    yield "data: [DONE]\n\n"


async def _stream_tool_call(model: str) -> AsyncIterator[str]:
    yield _chunk(model, {"role": "assistant", "content": None})
    yield _chunk(
        model,
        {
            "tool_calls": [
                {
                    "index": 0,
                    "id": "call_mock_tool_1",
                    "type": "function",
                    "function": {"name": TOOL_NAME, "arguments": ""},
                }
            ]
        },
    )
    if DELAY_SECONDS:
        await asyncio.sleep(DELAY_SECONDS)
    yield _chunk(model, {"tool_calls": [{"index": 0, "function": {"arguments": "{}"}}]})
    yield _chunk(model, {}, "tool_calls")
    yield "data: [DONE]\n\n"


def _reply_segments(messages: list[dict]) -> list[str]:
    user_text = _last_message(messages, "user")
    tool_result = _has_tool_result(messages)
    if tool_result is not None:
        return [f"The tool returned: {tool_result}. "]
    if "[[blocked]]" in user_text:
        return list(BLOCKED_SEGMENTS)
    if "guarantee" in user_text.lower():
        return list(GUARANTEE_SEGMENTS)
    knowledge = knowledge_segments(messages, _content_text)
    if knowledge:
        return knowledge
    return list(NORMAL_SEGMENTS)


def _wants_tool(messages: list[dict]) -> bool:
    return "[[tool]]" in _last_message(messages, "user")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/models")
async def models() -> dict:
    return {
        "object": "list",
        "data": [
            {"id": "mock-model", "object": "model", "owned_by": "bridge-agents"},
            {"id": "mock-embedding", "object": "model", "owned_by": "bridge-agents"},
        ],
    }


@app.post("/v1/embeddings")
async def embeddings(payload: dict[str, Any]) -> JSONResponse:
    """Return deterministic embeddings for the requested input text(s)."""
    raw_input = payload.get("input")
    texts = raw_input if isinstance(raw_input, list) else [raw_input or ""]
    data = [
        {
            "object": "embedding",
            "index": position,
            "embedding": embedding_vector(str(text), EMBEDDING_DIMENSION),
        }
        for position, text in enumerate(texts)
    ]
    return JSONResponse(
        {
            "object": "list",
            "data": data,
            "model": payload.get("model") or "mock-embedding",
            "usage": {"prompt_tokens": 0, "total_tokens": 0},
        }
    )


@app.post("/v1/moderations")
async def moderations(payload: dict[str, Any]) -> JSONResponse:
    """Deterministic moderation scenario used by the sanitize-node tests."""
    raw = payload.get("input")
    texts = raw if isinstance(raw, list) else [raw or ""]
    flagged = any("[[moderation]]" in str(text).lower() for text in texts)
    return JSONResponse(
        {
            "id": "modr-mock",
            "model": payload.get("model") or "omni-moderation-latest",
            "results": [
                {
                    "flagged": flagged,
                    "categories": ({"violence": True} if flagged else {"violence": False}),
                    "category_scores": {"violence": 1.0 if flagged else 0.0},
                }
            ],
        }
    )


@app.post("/v1/chat/completions")
async def chat_completions(payload: dict[str, Any]):
    """Answer one completion request using the deterministic scenarios."""
    messages = payload.get("messages") or []
    model = payload.get("model") or "mock-model"
    stream = bool(payload.get("stream"))

    if _is_review_request(messages):
        draft = _last_message(messages, "human") or _last_message(messages, "user")
        blocked = "guarantee" in draft.lower() or "[[blocked]]" in draft
        verdict = (
            {"normal": False, "reason": "The draft promises a refund."}
            if blocked
            else {"normal": True}
        )
        content = json.dumps(verdict)
        if stream:
            return StreamingResponse(_stream_text(model, [content]), media_type="text/event-stream")
        return JSONResponse(_completion(model, content))

    if _wants_tool(messages) and _has_tool_result(messages) is None:
        if stream:
            return StreamingResponse(_stream_tool_call(model), media_type="text/event-stream")
        return JSONResponse(_tool_call_completion(model))

    segments = _reply_segments(messages)
    if stream:
        return StreamingResponse(_stream_text(model, segments), media_type="text/event-stream")
    return JSONResponse(_completion(model, "".join(segments)))

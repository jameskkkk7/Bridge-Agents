# Mock model protocol

`mock/` is a tiny FastAPI service that speaks the OpenAI chat completions API
(`POST /v1/chat/completions`). It exists so the demo runs with **no API key and
no external network calls**, while still exercising every runtime path.

Environment:

| Variable | Default | Meaning |
|---|---|---|
| `MOCK_DELAY_MS` | `25` | Delay between streamed segments (milliseconds) |

## Request shapes

The service inspects the request and answers deterministically:

| Scenario | Trigger | Behaviour |
|---|---|---|
| Normal reply | anything else | Two or three short text segments, streamed as SSE when `stream=true` |
| Refund promise | user message contains `guarantee` | Reply contains "we guarantee", so a review node can reject it |
| Explicit block | user message contains `[[blocked]]` | Reply contains the marker, so a review node rejects it |
| Tool call | user message contains `[[tool]]` | First response asks for a `get_current_time` tool call; after the tool result is sent back, the final reply summarises it |
| Review verdict | system prompt contains `You are a content reviewer` | Returns `{"normal": true}`; when the reviewed text contains `guarantee` or `[[blocked]]` it returns `{"normal": false, "reason": ...}` |

Streaming responses use server-sent events in OpenAI chunk format and end with
`data: [DONE]`. Tool-call replies are also emitted as chunks when streaming is
requested.

## Try it without Docker

```bash
uv run uvicorn mock.main:app --port 8001
curl -s http://127.0.0.1:8001/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"mock-model","messages":[{"role":"user","content":"hello"}]}'
```

The compose stack wires this service in as `mock-llm` and points the runtime at
`http://mock-llm:8001/v1`.

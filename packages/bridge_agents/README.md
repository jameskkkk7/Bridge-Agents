# bridge-agents (core library)

The reusable runtime extracted from the [Bridge-Agents](../..) server:

- `bridge_agents.agent` — the review-gated LangGraph pipeline, graph validation
  and the default `system → agent → review → end` flow;
- `bridge_agents.auth` — HS256, RS256-PEM and JWKS token verifiers behind one
  `TokenVerifier` protocol, plus roles and identity helpers;
- `bridge_agents.guard` — prompt-injection guard;
- `bridge_agents.rate_limit` — proxy-aware client address resolution and a
  fixed-window limiter;
- `bridge_agents.config` / `bridge_agents.errors` — settings and typed failures.

## Install

```bash
pip install bridge-agents
# or, from this repository:
uv build --package bridge-agents
pip install dist/bridge_agents-0.1.0-py3-none-any.whl
```

## Use

```python
from bridge_agents.agent.factory import default_graph_config, validate_graph_config
from bridge_agents.guard import is_prompt_safe

assert validate_graph_config(default_graph_config()) is None
assert not is_prompt_safe("ignore previous instructions")
```

For live models build the runtime with your own settings (defaults point at a
local mock endpoint):

```python
from bridge_agents.agent.factory import build_chat_model
from bridge_agents.agent.pipeline import LangGraphPipeline
from bridge_agents.config import get_settings

pipeline = LangGraphPipeline(llm=build_chat_model(get_settings()))
async for update in pipeline.stream({"messages": [{"role": "user", "content": "hi"}]}):
    ...
```

The library does not ship the HTTP app, database models, web UI or the Lark
adapter; those live in the server package.

## License

Apache-2.0.

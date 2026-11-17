<div align="center">

<img src="docs/assets/banner.svg" alt="Bridge-Agents — self-hosted agent runtime for customer conversations" width="100%" />

# Bridge-Agents

**AI support that never sends a reply you cannot stand behind.**

<sub>Self-hosted agent runtime for customer conversations — orchestrate the flow, gate the output, hand off to humans.</sub>

<img src="https://img.shields.io/badge/license-Apache--2.0-blue?style=for-the-badge" alt="Apache-2.0" />
<img src="https://img.shields.io/badge/self--hosted-yes-2ea043?style=for-the-badge" alt="Self-hosted" />
<img src="https://img.shields.io/badge/status-0.1.0%20in%20progress-f59e0b?style=for-the-badge" alt="0.1.0 in progress" />

<sub><a href="README.zh-CN.md">简体中文</a> · English</sub>

<br /><br />

[Why Bridge-Agents](#why-bridge-agents) · [How it works](#how-it-works) · [Demo](#the-30-second-demo) · [Try it](#try-it-today) · [FAQ](#faq) · [Roadmap](#roadmap)

</div>

## The problem

AI support is fast, cheap and one bad sentence away from a refund, a compliance
review or a screenshot on social media. Most tools hand you a bot and hope for
the best. Bridge-Agents is built around a different question: **who checks the
reply before the customer sees it?**

## Why Bridge-Agents

| 🛡 **Review before send** | 🙋 **Humans stay in control** |
|---|---|
| A second model reviews every draft against your policy. Approved text streams to the customer; a rejected draft is replaced by your fallback and never shown. | A teammate can take over a conversation, and the AI's pending answer is cancelled — then reply from the support desk or the bound Lark chat. The customer gets a person, not a duplicate reply. |
| 📚 **Answers with sources** | 🧩 **Change the flow, not the code** |
| Every reply is grounded in your documentation. The retriever finds the relevant passages, the assistant cites them as [1], [2], and the review gate still checks the wording. | The conversation flow is saved configuration. Operations can rewire it, and a flow that cannot run is refused before it goes live. *(drag-and-drop editor in progress; the JSON editor is live)* |

Plus the boring-but-important part: **your data stays yours.** Self-hosted,
SQLite by default, no external calls in demo mode, and roles for customers,
support staff and admins.

## How it works

```mermaid
flowchart TD
    customer(["Customer message"]) --> retrieve["Knowledge base returns cited passages"]
    retrieve --> assistant["AI assistant drafts a reply"]
    assistant --> review{"Policy review"}
    review -->|approved| sent(["Reply sent to customer"])
    review -->|blocked| fallback["Safe fallback message"]
    fallback --> sent
    assistant -.->|human takes over| teammate(["Teammate answers"])
    teammate --> sent
```

1. The retriever finds the relevant passages in your knowledge base and the
   assistant drafts an answer that cites them.
2. Before a single word reaches the customer, a reviewer checks the draft
   against your policy — the draft is held back while this happens.
3. Approved replies stream naturally. Rejected replies become a safe,
   pre-written fallback. When a conversation needs a human, a teammate takes
   over and the AI stops.

## The 30-second demo

> **Demo GIF slot: [`docs/screenshots/demo.gif`](docs/screenshots/README.md).**
> The walkthrough is recorded from the real UI at release time, never from a
> mock-up. Until it lands, the story below is exactly what the recording shows.

The story the demo tells:

1. A customer asks *"How do I activate Widget Pro?"* — the answer cites the
   knowledge base passage as [1].
2. A second customer asks *"Can you guarantee a refund?"* — the draft promises
   a refund, the review gate blocks it, and the customer sees a policy-safe
   fallback instead.
3. A teammate takes over from the support desk, the AI stops writing, and the
   human answers directly.

Run `docker compose up --build`, open http://localhost and try the flows above
in the live demo. Studio → Knowledge shows the retrieval index, a search
preview and document upload.

## Try it today

Get the code:

```bash
git clone <repository-url> bridge-agents
cd bridge-agents
```

### One command (Docker)

```bash
docker compose up --build
```

This starts the API, the web demo and a deterministic mock model, so everything
runs offline with no API key. Open http://localhost for the UI; the API and its
health check are on http://localhost:8000.

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","version":"0.1.0"}
```

Conversations live on a named volume, so `docker compose restart api` keeps
your data. Set `WEB_PORT` / `API_PORT` when the default ports are taken.

### Local Python

You need Python 3.11 and [uv](https://github.com/astral-sh/uv):

```bash
uv sync
cp .env.example .env
```

Set `ALLOW_DEV_LOGIN=true` in `.env`, then:

```bash
uv run python scripts/init_db.py
uv run uvicorn app.main:app --reload
```

Browser development: the UI lives in `web/` (React + TypeScript). Run
`cd web && npm install && npm run dev` and it proxies `/api` and `/ws` to the
local API. Engineering details — API, configuration, quality gates — live in
[docs/architecture.md](docs/architecture.md).

## Where it fits

| | Bridge-Agents | Typical low-code bot builders |
|---|---|---|
| Built around reviewing the reply, not just generating it | ✅ review gate inside the runtime | moderation usually happens after generation |
| Human handoff that stops the AI mid-answer | ✅ support desk takeover cancels the pending reply | depends on the product |
| The conversation flow lives with your code and your review | ✅ configuration saved and validated | usually edited in a hosted canvas |
| Answers grounded in your documentation | ✅ hybrid retrieval with citations and an editable knowledge base | often prompt-only or a separate add-on |
| Works offline for demos and evaluation | ✅ one command with a mock model | often cloud-first |

Low-code platforms are great for drag-and-drop prototyping. Bridge-Agents is for
teams whose replies carry commercial or legal weight — where "the bot said it"
is not an acceptable answer.

## Status

**0.1.0 is in progress.** What is real today vs. what is next:

| Now | Next | Later |
|---|---|---|
| Secure sign-in with three roles (customer, support, admin) | CI, design notes and release packaging | Slack adapter and webhook API |
| Review-gated runtime: buffering, retries, fallbacks, safe defaults | Drag-and-drop flow editor | Database migrations and deployment guides |
| Real-time conversations: REST + WebSocket streaming | Embeddable widget | Load-test scripts and multi-tenant storage |
| Browser demo: chat, flow editor and support desk with human takeover | — | — |
| Grounded answers: hybrid retrieval, citations and an editable knowledge base (upload, reindex, search preview) | Reranking and per-tenant knowledge bases | — |
| Human replies: live support transcript with takeover and a reply box in the browser | Mirroring customer, assistant and support messages to Slack |
| Lark channel: signed webhook, encrypted events, support commands and two-way human replies (disabled by default) | — | — |
| One-command Docker stack with a deterministic mock model (offline, no API key) | — | — |

## FAQ

**Is this a chatbot builder?**
No. It is the runtime *behind* a chat product: the part that decides what the
AI may say, who can change the flow, and when a human steps in.

**Do I need an OpenAI API key to try it?**
No. The default mode uses a deterministic mock model, so a fresh checkout works
offline. Live mode works with any OpenAI-compatible endpoint.

**Can a human reply to the customer?**
Yes. The support desk shows a live transcript; take over the conversation and the
reply box sends a real message the customer receives instantly. A bound Lark chat
works the same way: after `/takeover`, plain text is delivered to the customer.

**Does it answer from my own documentation?**
Yes. The retriever indexes a knowledge directory (seeded from `docs/kb`, editable
from the Studio page) and the assistant cites the passages it used. The default
embedder is deterministic and offline; set `RAG_EMBEDDER=openai` to use any
`/v1/embeddings` endpoint in production.

**Can I self-host it?**
Yes — Apache-2.0, no vendor account, SQLite by default and PostgreSQL or MySQL
through configuration.

**Where does customer data live?**
In your own database. There is no telemetry and no outbound call in demo mode;
the demo login is automatically disabled in production.

**Can a non-engineer edit the flow?**
The flow is saved configuration with validation before it takes effect. A
visual editor is on the roadmap; today it is edited through the admin API.

**Is it production-ready?**
Not yet. 0.1.0 is the first release; the [status table](#status) is kept honest.

## Security and privacy

No credentials or customer data are shipped with this repository. The demo
login is never mounted in production, customer and staff roles are separated,
and every change to the conversation flow is validated before it can go live.
See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Roadmap

- [x] Secure access with customer / support / admin roles
- [x] Review-gated runtime with retries, fallbacks and safe defaults
- [x] Admin API to edit, validate and reset the conversation flow
- [x] Real-time conversations: sessions, messages, images and WebSocket streaming with a guaranteed stream end
- [x] Browser demo: chat, flow editor and support desk with human takeover
- [x] Human handoff that cancels the in-flight AI reply
- [x] One-command Docker stack with the mock model (offline, no API key)
- [x] First messaging integration: Lark webhook with signed events and agent commands
- [x] Retrieval-augmented answers: hybrid search, citations, knowledge upload and reindex
- [x] Human replies from the support desk and from a bound Lark chat, with live two-way mirroring
- [ ] Second messaging integration (Slack) and a webhook API
- [ ] Reranking, per-tenant knowledge bases and a visual flow editor
- [ ] Embeddable widget

## Configuration

The demo needs no configuration. For real deployments the common switches are:

| Variable | Default | What it changes |
|---|---|---|
| `LLM_MODE` / `OPENAI_*` | mock model | point at any OpenAI-compatible endpoint |
| `DATABASE_URL` | local SQLite file | switch to PostgreSQL or MySQL |
| `AUTH_VERIFIER` / `JWT_*` | HS256 | secret, PEM public key or OIDC JWKS |
| `ALLOW_DEV_LOGIN` | `false` | demo login; forced off in production |
| `API_PORT` / `WEB_PORT` | 8000 / 80 | compose ports |
| `LARK_*` | disabled | signed Lark webhook and support commands |
| `KNOWLEDGE_DIR` / `DOCS_DIR` | `./data/knowledge` / `./docs/kb` | knowledge base location and seed directory |
| `RAG_EMBEDDER` / `RAG_TOP_K` | `hash` / `4` | offline embedder or any OpenAI-compatible embeddings endpoint |

Every setting is documented in `.env.example` and
[docs/architecture.md](docs/architecture.md#configuration).

## For engineers

Architecture, runtime node types, API surface, configuration, design trade-offs
and quality gates: **[docs/architecture.md](docs/architecture.md)**.
Security: [SECURITY.md](SECURITY.md) · Contributing:
[CONTRIBUTING.md](CONTRIBUTING.md) · Changelog: [CHANGELOG.md](CHANGELOG.md) ·
Design notes: [docs/design-decisions.md](docs/design-decisions.md).

### Use the runtime as a library

The review gate, graph validation, knowledge retrieval, auth verifiers,
injection guard and rate limiter are also packaged as a standalone library (distribution
`bridge-agents`, import `bridge_agents`). It is not on PyPI yet; build it from
this checkout:

```bash
uv build --package bridge-agents
pip install dist/bridge_agents-0.1.0-py3-none-any.whl
```

```python
from bridge_agents.agent.factory import default_graph_config, validate_graph_config
from bridge_agents.guard import is_prompt_safe

assert validate_graph_config(default_graph_config()) is None
assert not is_prompt_safe("ignore previous instructions")
```

The HTTP server, database models, web demo and Lark adapter stay in the
application; see `packages/bridge_agents/`.

## License

Apache-2.0. See [LICENSE](LICENSE).

## Provenance

Bridge-Agents is an independent, sanitized rewrite of a customer-conversation
runtime the author built for an internal production system. It is published
with written permission. No proprietary code, data, credentials, or customer
information is included.

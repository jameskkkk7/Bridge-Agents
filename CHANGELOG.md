# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-11-16

Initial preview release: a self-hosted, review-gated agent runtime for customer
conversations, with a deterministic offline demo.

### Added

- **Runtime:** LangGraph pipeline with `system`, `retrieval`, `agent`, `tools`,
  `custom`, `sanitize` and `review` node kinds; retry, fallback and pass-through
  policies; Mermaid export; compile-before-save graph validation.
- **Retrieval (RAG):** heading-aware knowledge chunks, hybrid vector + lexical
  search with citations, deterministic offline embedder (or any OpenAI-compatible
  `/v1/embeddings` endpoint), admin status/search/upload/reindex API, and a Studio
  knowledge panel.
- **Review gate:** buffered streaming, rejected drafts never reach the client,
  reviewer output is not leaked, and retries are bounded.
- **Provider moderation:** the sanitize node keeps its local banned-word hard gate
  and can additionally call OpenAI-compatible `/v1/moderations`, Azure AI Content
  Safety, Google Perspective, Alibaba Cloud Content Moderation or Tencent Cloud
  TMS for the latest assistant draft, with fallback text and fail-open/closed
  policy. The Alibaba Cloud and Tencent Cloud signers are validated against the
  official signature examples.
- **Auth:** HS256, RS256-PEM and JWKS verifiers behind one protocol; three roles
  (customer, support, admin); dev login only outside production.
- **Conversations:** session, message and image APIs; WebSocket streaming with a
  guaranteed `stream_end`, reconnect support and per-user rate limiting.
- **Support desk:** admin conversation list, transcript, status changes and
  human takeover that cancels the in-flight AI reply.
- **Human replies:** live support transcript over a staff websocket, takeover and
  a reply box that delivers messages to the customer instantly.
- **Lark channel:** signed webhook, AES-encrypted events, command handling for
  `/takeover`, `/release`, `/status` and `/help`; plain-text agent replies after
  takeover reach the customer; customer/assistant/support messages mirror into
  the bound chat; disabled and offline by default.
- **Demo stack:** `docker compose up --build` starts the API, a deterministic
  OpenAI-compatible mock model and the web demo; no API key required.
- **Web demo:** customer chat, Studio (JSON flow editor with Mermaid preview and a
  knowledge panel), and a support desk with live transcript, takeover and replies.
- **Bilingual UI:** English and Simplified Chinese dictionaries, a persisted
  EN / 中文 switch, browser-language detection and localized system messages.
- **Two entry points:** `/` is the customer chat (no staff navigation) and
  `/admin` is the staff portal with the support desk and Studio at
  `/admin/studio`; the legacy `/graph` URL redirects.
- **Runtime settings:** Studio → Settings can change the OpenAI-compatible
  endpoint, model, sampling settings and API key (encrypted at rest, write-only
  over the API) and edit the support prompt; saving hot-swaps the pipeline.
- **Responsive UI:** phone and tablet layouts for the customer chat, support
  desk and Studio (breakpoints at 900/640/380 px, safe-area insets, 16 px form
  text, full-width composers and no horizontal scrolling).
- **Refreshed visual design:** light and dark themes from one token set, pill
  navigation and controls, restrained surfaces and self-hosted Kumbh Sans,
  Noto Sans SC and Roboto Mono fonts; the theme choice is remembered and applies
  before first paint.
- **Component system:** migrated the browser demo to Tailwind CSS 4 + shadcn/ui
  on Radix primitives (Button, Card, Input, Textarea, Label, Badge, Tabs) with
  lucide icons, replacing the hand-written stylesheet.
- **Visual flow editor:** React Flow canvas for the Studio flow: wide left-to-right
  graph layout with a full-width canvas and the node inspector below it, node
  palette, drag/connect with condition handles, auto layout, local validation,
  saved positions, JSON fallback and lazy loading.
- **Library:** the core runtime is also packaged as a standalone
  `bridge-agents` distribution (`packages/bridge_agents`, import
  `bridge_agents`): LangGraph pipeline and graph validation, token verifiers,
  injection guard, settings and typed errors.
- **Demo chat experience:** reference-style composer with attachment sending,
  a conversation-history sidebar with multiple conversations, automatic titles
  from the first message, and a no-sign-in demo mode.
- **Demo customer identity:** customers enter a nickname before chatting; each
  browser receives an isolated demo account, the support desk shows the
  nickname and the assistant addresses the customer by name.
- **Support desk clarity:** AI replies and human teammate replies are labelled
  separately (`sender_kind` in the API and transcript), with an AI/human mode
  badge per conversation.
- **Model providers:** Studio -> Settings can configure OpenAI, Azure OpenAI
  (native client) and mainstream OpenAI-compatible vendors (DeepSeek, Qwen,
  Kimi, GLM, Doubao, ERNIE, MiniMax, SiliconFlow, OpenRouter, Gemini, Ollama
  and custom gateways) through provider presets.
- **UI polish:** rounded dropdown menus, bilingual provider/prompt copy and a
  wider customer layout for the conversation sidebar.
- **Developer experience:** a `bridge-agents` CLI (`demo`, `serve`, `init-db`,
  `doctor`, `version`), a single-port mode that serves the built web UI from the
  API, `make demo` for a one-command offline demo, and a Makefile with the
  common install/test/lint/build/package tasks.
- **Deployment:** the server distribution is now `bridge-agents-server` (pinned
  core version, `[postgres]`/`[mysql]` extras) and the GUI ships as a separate
  static release artifact. Add TOML configuration with standard precedence,
  `init`/`config check`/`serve --config` commands, `/api/v1/meta` version
  handshake, systemd/nginx templates and an embeddable `AgentRuntime` façade
  with testing fakes.
- **Support prompt:** the shipped agent prompt is a complete customer-service
  playbook covering identity, grounded answers with citations, tone,
  policy limits, tool use, safety/privacy, human handover, formatting and
  uncertainty handling.
- **Demo knowledge base:** eight additional customer-support articles cover
  accounts and workspaces, billing and invoices, refunds and cancellations,
  desktop sync, sign-in/SSO troubleshooting, API and webhooks, security and
  compliance, and support SLAs (10 documents, 64 indexed chunks).
- **Provider addresses:** every Studio provider preset was re-checked against
  the vendors' current official documentation (DeepSeek base URL without /v1,
  MiniMax's api.minimax.cn domain, Anthropic's official OpenAI SDK compatibility
  endpoint, Azure resource endpoint, international alternatives). Providers
  without a compatible model-list API fall back to a manual model field.
- **Model settings:** model names are no longer typed by hand. Once an API key
  is available (new, stored or environment), Studio asks the provider for its
  models — OpenAI-compatible `/models` or Azure deployments — and offers a
  refreshable dropdown. The catalog endpoint is staff-only and never returns
  the key.
- **Knowledge base:** clicking a document in Studio opens a read-only full-text
  preview (backed by `GET /api/v1/admin/knowledge/documents/{name}`); staff-only,
  with size and passage counts, Escape/backdrop close.
- **Release engineering:** a version consistency check, a tag-driven GitHub
  release workflow (wheels, static GUI archive, GHCR server/web images and a
  GitHub Release) and a manual PyPI trusted-publishing workflow, documented
  in `docs/releasing.md`.
- **Quality:** 326 offline tests, 91% combined line coverage of `app/core` and
  the library, ruff, a repository sanitisation gate and CI for lint, tests,
  secrets and web build.

### Fixed

- **Provider moderation hardening:** malformed 200 responses and unexpected
  provider exceptions now follow the configured fail-open/fail-closed policy
  instead of crashing the reply or silently passing; enabling a provider without
  its credentials is surfaced instead of skipped; Perspective API keys are kept
  out of logs; long replies are split at each provider's text limit (600
  characters for Alibaba Cloud, 10 000 for Azure and Tencent Cloud); provider
  URLs, ranges and unknown provider names are validated on save; each vendor's
  key is only used for that vendor; the optional `MODERATION_ALLOWED_HOSTS`
  allow-list restricts provider destinations.
- **Moderation streaming gate:** text is buffered until every gate node that can
  actually run (provider-backed sanitize and/or review, including parallel
  branches and conditional routing) has produced a verdict, so a blocked draft
  is never streamed to the customer before the fallback replaces it.
- **Upgrade note:** Azure and Perspective now require their dedicated
  `MODERATION_AZURE_KEY` / `MODERATION_PERSPECTIVE_KEY`. `MODERATION_API_KEY` is
  only used by the OpenAI-compatible adapter; it used to be a silent fallback for
  the other two providers, which would leak one vendor's key to another. Set the
  dedicated variables before upgrading.
- **Studio numeric fields:** clearing a provider threshold/severity/timeout no
  longer writes `0` (which flagged every reply); values are edited as text and
  clamped to their documented ranges.

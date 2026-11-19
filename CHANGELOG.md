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
- **Visual flow editor:** React Flow canvas for the Studio flow: top-down graph
  layout, node palette, drag/connect with condition handles, per-node inspector,
  auto layout, local validation, saved positions, JSON fallback and lazy loading.
- **Library:** the core runtime is also packaged as a standalone
  `bridge-agents` distribution (`packages/bridge_agents`, import
  `bridge_agents`): LangGraph pipeline and graph validation, token verifiers,
  injection guard, rate limiter, settings and typed errors.
- **Quality:** 233 offline tests, 92% combined line coverage of `app/core` and
  the library, ruff, a repository sanitisation gate and CI for lint, tests,
  secrets and web build.

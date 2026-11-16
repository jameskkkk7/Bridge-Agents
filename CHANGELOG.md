# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-11-16

Initial preview release: a self-hosted, review-gated agent runtime for customer
conversations, with a deterministic offline demo.

### Added

- **Runtime:** LangGraph pipeline with `system`, `agent`, `tools`, `custom`,
  `sanitize` and `review` node kinds; retry, fallback and pass-through policies;
  Mermaid export; compile-before-save graph validation.
- **Review gate:** buffered streaming, rejected drafts never reach the client,
  reviewer output is not leaked, and retries are bounded.
- **Auth:** HS256, RS256-PEM and JWKS verifiers behind one protocol; three roles
  (customer, support, admin); dev login only outside production.
- **Conversations:** session, message and image APIs; WebSocket streaming with a
  guaranteed `stream_end`, reconnect support and per-user rate limiting.
- **Support desk:** admin conversation list, transcript, status changes and
  human takeover that cancels the in-flight AI reply.
- **Lark channel:** signed webhook, AES-encrypted events, command handling for
  `/takeover`, `/release`, `/status` and `/help`; disabled and offline by default.
- **Demo stack:** `docker compose up --build` starts the API, a deterministic
  OpenAI-compatible mock model and the web demo; no API key required.
- **Web demo:** customer chat, JSON flow editor with Mermaid preview, and a
  support desk with takeover.
- **Library:** the core runtime is also packaged as a standalone
  `bridge-agents` distribution (`packages/bridge_agents`, import
  `bridge_agents`): LangGraph pipeline and graph validation, token verifiers,
  injection guard, rate limiter, settings and typed errors.
- **Quality:** 177 offline tests, 91% combined line coverage of `app/core` and
  the library, ruff, a repository sanitisation gate and CI for lint, tests,
  secrets and web build.

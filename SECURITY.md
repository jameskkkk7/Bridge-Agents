# Security Policy

## Supported versions

This project is pre-1.0: security fixes land on the `main` branch only.

## Reporting a vulnerability

Please do not open a public issue for security problems.
Use GitHub's private vulnerability reporting (Security → Advisories →
Report a vulnerability) on this repository. We aim to acknowledge reports
within a few days.

## Scope notes

- The default LLM mode is `mock`; live mode talks to whichever
  OpenAI-compatible endpoint you configure.
- The demo login endpoint under `/api/v1/auth/dev-login` is only mounted when
  `ALLOW_DEV_LOGIN=true` and the environment is not `production`.
- No credentials or customer data are shipped with this repository.
- Runtime model API keys entered in Studio → Settings are encrypted in the
  database with a key derived from `JWT_SECRET` and are never returned by the
  API. Set a strong, stable `JWT_SECRET`; rotating it invalidates stored model
  keys until they are re-entered.
- The Lark webhook verifies the request signature before parsing, decrypts
  encrypted events, and only accepts text messages from open ids listed in
  `LARK_AGENT_OPEN_IDS`. With `LARK_ENABLED=false` it returns 404 and makes no
  outbound request.
- WebSocket authentication uses a query-string token in the demo. Terminate TLS
  in front of the API, redact query strings from proxy access logs, and prefer
  short-lived socket tickets outside the demo.
- Rate limiting trusts `X-Real-IP` / `X-Forwarded-For` only as far as your
  reverse proxy overwrites them; configure the proxy accordingly.

## Hardening checklist for production

- Set a long random `JWT_SECRET` (HS256) or use RS256/JWKS.
- Set `APP_ENV=production` and keep `ALLOW_DEV_LOGIN=false`.
- Use PostgreSQL or MySQL instead of the bundled SQLite file.
- Put the API behind a TLS-terminating reverse proxy with trusted forwarded
  headers and request-size limits.
- Supply model, database and channel credentials through environment variables
  or a secret manager — never commit them.

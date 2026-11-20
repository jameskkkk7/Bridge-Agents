# API and webhooks

## API access

Workspace admins create API tokens under **Settings → Developer → API tokens**.
Tokens are shown once; store them in a secret manager and send them as
`Authorization: Bearer <token>`. Scopes limit a token to specific resources
(for example `boards:read`, `boards:write`, `members:read`, `webhooks:manage`).
Revoke a token immediately if it leaks; revocation takes effect within seconds.

Base URL: `https://api.widget.example/v1`. All requests use JSON and HTTPS. API
versions are part of the path; breaking changes are introduced only with a new
version and a migration period.

## Rate limits

Limits are per workspace token and per minute: 120 requests per minute for
reads and 30 requests per minute for writes, with a short burst allowance. When
a limit is exceeded the API returns `429 Too Many Requests` with a
`Retry-After` header. Retry with exponential backoff and jitter; do not retry
write requests blindly without checking whether the first attempt succeeded.

Pagination uses cursor-based links (`next_cursor`) and returns at most 100 items
per page. List endpoints support `limit`, `cursor` and `updated_since` filters.

## Common errors

- `401 unauthorized` — missing, expired or revoked token.
- `403 forbidden` — token lacks the required scope, or the workspace is
  read-only because of a billing issue.
- `404 not_found` — the resource does not exist or is not visible to the token.
- `409 conflict` — optimistic-concurrency mismatch; re-read the resource and
  retry with the current version token.
- `422 validation_failed` — the request body did not match the schema; the
  response lists field-level errors.
- `429 too_many_requests` — respect `Retry-After`.
- `5xx` — retry idempotent requests with backoff; check the status page before
  contacting support.

## Webhooks

Configure endpoints under **Settings → Developer → Webhooks**. The endpoint must
accept `POST` requests, return a 2xx status within ten seconds, and tolerate
duplicate deliveries. Deliveries are retried up to eight times over 24 hours
with exponential backoff; persistent failures disable the endpoint and notify
workspace admins.

Every delivery carries:

- `X-Widget-Event` — event name, for example `board.created`,
  `member.updated`, `export.ready`.
- `X-Widget-Delivery` — unique delivery identifier; use it for idempotency.
- `X-Widget-Signature` — `sha256=` HMAC of the raw request body using the
  endpoint signing secret.

Verify the signature against the raw body before parsing JSON, and reject
deliveries whose timestamp is older than five minutes. Rotate signing secrets
from the webhook settings; during rotation both the old and new secret are valid
for 24 hours.

## Integration testing

Use a staging workspace and a dedicated token for automated tests. Webhook
endpoints can be replayed from **Recent deliveries**, and the API returns request
identifiers in the response headers; include them in support requests.

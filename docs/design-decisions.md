# Design decisions

The choices below shape the runtime more than any single file. Each entry names
the trade-off, because a decision without a cost is usually a preference.

## 1. The review node buffers streamed output

**Decision:** while a review node is wired after an agent, its output is buffered
and only released when the reviewer approves the draft. A rejected draft is
replaced by the configured fallback or retried, and the reviewer's own tokens
never reach the client.

**Why:** a rejected sentence must never flash on a customer's screen, even for a
few hundred milliseconds. "We streamed it but deleted it" is not a guarantee.

**Cost:** the first visible token arrives later whenever the gate is present.
Conversations that do not need review can omit the node and stream immediately.

## 2. Takeover cancels the in-flight reply

**Decision:** enabling human takeover cancels the pending generation task for
that conversation, and a cancelled task still emits `stream_end`.

**Why:** without cancellation a human reply can be racing an AI answer that was
already being generated. The customer would see two answers, or the AI would
answer after the human did.

**Cost:** cancellation is cooperative: a provider that ignores an aborted
request still consumes the request until it finishes. The client state remains
correct, but upstream tokens may be wasted.

## 3. The graph is compiled before it is saved

**Decision:** `PUT /admin/runtime-config/agent-graph-config` builds the graph
first and only persists configuration that compiles and validates.

**Why:** route mistakes become save-time errors instead of production errors.
An operator sees "edge target does not exist" while editing, not at 2 a.m.

**Cost:** saving does real work and is slightly slower. The stored shape is also
constrained by the supported node types instead of accepting arbitrary JSON.

## 4. Rate limiting uses `X-Real-IP` when present

**Decision:** the client IP is resolved from `X-Real-IP`, then the right-most
`X-Forwarded-For` hop, and only then the socket address.

**Why:** behind nginx every websocket looks like it comes from the same proxy
address. Without forwarding awareness all users would share one rate-limit
bucket.

**Cost:** headers are only trustworthy behind a proxy that overwrites them. A
public deployment must terminate TLS and set these headers itself; tests cover
the resolution order.

## 5. UUIDs are stored as fixed-width strings

**Decision:** primary keys are UUID strings in `String(36)` columns rather than
a 16-byte binary representation.

**Why:** the schema stays portable across SQLite, MySQL and PostgreSQL, and
database rows stay readable while debugging. For a single-tenant support tool
the storage difference is negligible.

**Cost:** roughly twice the index size of a binary UUID. A high-volume tenant
could switch to a native UUID type later without changing the API contract.

## 6. Mock LLM mode is the default

**Decision:** a fresh checkout points at a deterministic OpenAI-compatible mock
model, included in the compose stack, and no API key is required.

**Why:** the demo must be reproducible for reviewers and CI, and "get an API key
before you can see the product" is a bad first-run experience.

**Cost:** the mock is code that has to be kept in sync with the runtime's request
and streaming contract. Tests enforce that contract, and real providers still
need their own evaluation.

## 7. Three roles, no super-admin

**Decision:** the role set is customer (`USER`), support staff (`AGENT`) and
administrator (`ADMIN`). Support staff can read all conversations and take over;
only administrators can read the user directory.

**Why:** a fourth "super admin" role adds a privilege boundary without adding a
user-facing capability in v0.1. Fewer roles are easier to reason about.

**Cost:** separating staff management from support operations will need an
explicit admin action or a new role later; until then administrators do both.

## 8. Disabled demo login returns 404

**Decision:** when `ALLOW_DEV_LOGIN=false` or the environment is production, the
demo login route is not mounted at all, so it returns 404 rather than 403.

**Why:** an unmounted capability cannot be accidentally enabled by a mis-issued
token or a forgotten flag, and 404 avoids advertising an authentication bypass.

**Cost:** operators debugging configuration see "not found" instead of a clear
"disabled" message; the startup log and documentation have to carry that signal.

## 9. No migration tool in v0.1

**Decision:** schema bootstrap uses SQLAlchemy `create_all`; no Alembic in the
initial release.

**Why:** the demo is single-instance and its database is disposable. Shipping a
correct initial migration adds process before the schema is stable.

**Cost:** upgrades between versions will need either a reset or manual SQL. Any
real deployment before 1.0 should treat the schema as unstable; Alembic is the
first database task after it.

## 10. WebSocket tokens travel in the query string

**Decision:** the gateway authenticates with `?token=<jwt>` because the browser
WebSocket API cannot set an `Authorization` header.

**Why:** it keeps the browser client simple and matches how the demo is served.

**Cost:** tokens can appear in proxy access logs. Production deployments should
use short-lived, single-purpose socket tickets (or a cookie set by the same
origin), serve over TLS, and redact query strings in proxy logs.

## 11. Lark is disabled and offline until configured

**Decision:** the Lark adapter performs no outbound call unless
`LARK_ENABLED=true` and every credential, including the Encrypt Key, is present.
The webhook itself is hidden (404) while disabled.

**Why:** an unconfigured integration should be unable to leak data or generate
traffic. Signature verification also needs the encrypt key, so a half-configured
channel must fail closed.

**Cost:** turning the channel on requires a restart with complete configuration;
there is no partial "read-only" mode in v0.1.

## 12. The browser demo uses no UI framework

**Decision:** `web/` is React + TypeScript with hand-written CSS, under a hard
budget of 12 source files and 900 lines.

**Why:** the demo exists to prove the runtime, not to become a product surface.
A small codebase is reviewable and cannot quietly grow into a second project.

**Cost:** no component library, no drag-and-drop flow editor yet, and some
interaction patterns are implemented directly rather than reused.

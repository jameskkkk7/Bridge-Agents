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

## 13. Retrieval is a graph node, not hidden middleware

**Decision:** grounding is a `retrieval` node in the editable graph (default:
`system → retrieval → agent → review → end`), and the same knowledge base backs
the `search_docs` tool.

**Why:** operators can see what feeds the model, move retrieval before or after
other steps, lower the passage budget, or remove it for flows that do not need
it. The Mermaid export makes that visible without reading code.

**Cost:** every graph that wants grounding must route into the node, and the
node adds one lookup to the request path. Graphs without it behave exactly as
before.

## 14. Hybrid retrieval with a deterministic default embedder

**Decision:** the index blends cosine similarity from a hashed bag-of-terms
embedder (60%) with TF-IDF lexical matching (40%). `RAG_EMBEDDER=openai` swaps in
any `/v1/embeddings` endpoint without changing the rest of the pipeline.

**Why:** the demo and CI must run offline, and product names, error codes and
policy numbers are exact tokens that dense embeddings blur. The hybrid keeps
both signals; the lexical half also makes typos and stemming differences less
harmful, and scores are inspectable.

**Cost:** hashed embeddings are weaker than a trained model on paraphrases, and
the constant weights were tuned by hand on a small corpus. A production
deployment should use an embeddings endpoint and may need its own weights or a
reranker.

## 15. Citations are part of the prompt contract, and the gate still applies

**Decision:** retrieved passages are numbered and the agent is asked to cite
them as `[1]`, `[2]`; the review node reviews the finished answer exactly as
before.

**Why:** an answer that cannot point at a source is hard to audit, and the gate
must not be bypassed just because the reply looked grounded. The mock model
follows the same contract so the demo shows a real cited answer.

**Cost:** the model can still cite imprecisely, and citations add tokens to the
prompt and answer. The admin search preview exists so reviewers can check a
citation against the scored passages before trusting it.

## 16. Human replies reuse the message pipeline

**Decision:** a staff reply is an ordinary agent message: it is persisted by the
same message service, broadcast by the same session broadcaster and mirrored by
the same channel bridge, whether it comes from the support desk websocket or
from the bound Lark chat.

**Why:** a separate "human reply" table or endpoint would fork delivery,
ordering and channel mirroring, and the customer's client would need a second
code path. Reusing one pipeline keeps the transcript, websocket payload and
mirroring consistent for AI and human messages.

**Cost:** the API does not stop a staff reply while the AI is still generating;
the reviewer of this behaviour is takeover. The web composer disables itself
until takeover is on, and thinking about stricter server-side enforcement is a
v0.2 item (for example, reject staff messages while takeover is off).

## 17. Two entry points share one SPA bundle

**Decision:** the browser app has two shells with separate URLs: `/` is the
customer chat with no staff navigation, and `/admin` is the staff portal
(support desk plus Studio at `/admin/studio`). Both are served from the same
bundle and the same origin as the API.

**Why:** a customer should never see "Support desk" or "Studio" in their chat
window, and a support agent should not have to navigate past a customer chat
page to reach a conversation. Separate shells also make the screenshots and the
demo story match the two audiences, while keeping one deployable artifact.

**Cost:** staff pages are hidden, not isolated, in the browser; the real
boundary remains the token and the `AGENT`/`ADMIN` checks on every staff API.
A stronger deployment could serve the staff bundle on a different hostname
behind SSO, at the cost of a second build and deployment.

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

## 12. The browser demo uses Tailwind 4 + shadcn/ui

**Decision:** `web/` is React + TypeScript with Tailwind CSS 4 and shadcn/ui
components generated on top of Radix primitives (Button, Card, Input, Textarea,
Label, Badge, Tabs). The generated components are vendored in
`web/src/components/ui/` and styled through the token set in `index.css`.

**Why:** the earlier hand-written CSS was small but slow to extend, and matching
the reference product surface by hand meant reimplementing focus rings, tabs,
form states and dark-mode variants repeatedly. shadcn gives accessible Radix
behaviour and consistent Tailwind styling while the code stays ours; a hard
budget and one shared token set keep it from becoming a second product.

**Cost:** ~36 npm packages (Tailwind, Radix primitives, cva, clsx, merge) and a
larger JS/CSS bundle than the hand-written version; generated components are
ours to maintain. The mobile and i18n work still lives in our own code.

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

## 18. Model configuration is runtime data with an encrypted secret

**Decision:** the model endpoint, name, sampling settings and API key are stored
in the `settings` table; the environment provides defaults. Saving rebuilds the
pipeline so the change applies to the next message. The API key is encrypted
with Fernet using a key derived from `JWT_SECRET`, is write-only over the API,
and is removed by "reset to environment".

**Why:** changing a model should not require editing files and restarting a
container, and an operator needs one place to see which model is live. Keeping
the secret out of API responses avoids leaking it to the browser history, logs
or screenshots.

**Cost:** the secret's safety now depends on `JWT_SECRET` staying private; a
rotation makes stored model keys unreadable, which surfaces as "key not
configured" until re-entered. A production deployment may prefer a real secret
manager over database encryption.

## 19. The support prompt is the graph's system node

**Decision:** the prompt editor reads and writes the `system` node of the saved
graph instead of storing a second copy.

**Why:** two sources of truth would let the Flow JSON and the prompt editor
disagree, and the next save in either place would silently overwrite the other.
Keeping one copy means "save prompt" recompiles and activates the same graph the
Flow tab shows.

**Cost:** editing the prompt creates a saved graph even if the deployment was
running the built-in default (the response reports `saved_graph` so this is
visible). Prompt changes also touch every system node in a multi-system graph.

## 20. Mobile support is responsive CSS, not a second app

**Decision:** the three views share one responsive layout with breakpoints at
900, 640 and 380 px instead of shipping a separate mobile client or a native
app.

**Why:** the demo has to stay small enough to read in one sitting, and the
customer chat plus staff tools are mostly lists, forms and a message stream —
exactly what media queries handle well. One bundle also keeps the two entry
points, the i18n dictionaries and the API client in one place.

**Cost:** no native push notifications, offline mode or app-store presence, and
some interactions (a sticky composer above the soft keyboard) are approximations
of what a native app would do. A production mobile client would still want its
own build.

## 21. One UI with light and dark themes, and self-hosted fonts

**Decision:** both themes come from one set of CSS variables exposed as
Tailwind theme tokens; React only toggles the `.dark` class. Fonts are bundled
through Fontsource (Kumbh Sans, Noto Sans SC, Roboto Mono) instead of loaded
from a CDN.

**Why:** one component tree means both themes stay feature-complete and the
mobile/bilingual work is not duplicated. Self-hosting removes a third-party
runtime dependency, keeps the demo offline and gives Chinese and Latin text a
consistent typeface.

**Cost:** the Noto Sans SC package adds roughly 4.5 MB of Unicode-range font
files to the image (browsers download only the subsets they need) and the theme
needs care around images/code blocks. A CDN would cut build size but add an
external request and a privacy trade-off.

## 22. The visual flow editor is a view over the JSON graph

**Decision:** the Studio canvas uses React Flow to edit exactly the JSON graph
the runtime consumes. Node positions and display metadata live in the node
`config` object (ignored by the runtime), edges keep `condition` /
`source_handle`, and the JSON editor remains available as a fallback.

**Why:** one representation means a graph saved by dragging and a graph saved as
JSON are validated, compiled and executed the same way. Operators get direct
manipulation, while debugging and bulk edits still have a precise text view.

**Cost:** layout metadata leaks into the graph config (harmless but not part of
the runtime schema), client validation duplicates some backend rules, and React
Flow adds ~275 KB lazy-loaded JS. The editor is code-split so other pages stay
small.

## 23. Provider moderation complements the local hard gate

**Decision:** the sanitize node always applies the local banned-word list. An
optional provider check supports five adapters — OpenAI-compatible
`/v1/moderations`, Azure AI Content Safety, Google Perspective, Alibaba Cloud
TextModeration and Tencent Cloud TMS — for the latest assistant draft only,
replacing a flagged draft with a configurable fallback. Network failures,
unexpected provider payloads and missing credentials all raise a moderation
error; by default the reply fails open, while `provider_fail_open=false` turns
the same paths into the configured fallback. Long replies are split at each
provider's documented text limit, streamed text is held until the provider-backed
sanitize node has run, and saving a fail-closed node without its credentials is
rejected.

**Why:** the local list is deterministic, free and cannot be silently disabled
by an outage. Provider classifiers catch categories that a finite word list
cannot enumerate. Checking only the latest draft avoids re-billing the whole
conversation on every turn; a single, uniform failure path keeps one malformed
response from breaking the conversation.

**Cost:** one extra network call/latency for the sanitize node (more only when a
long reply must be split), provider false positives and an external dependency;
the operator can choose fail-closed, pin the provider URL/model per node and
restrict hosts with `MODERATION_ALLOWED_HOSTS`. API keys stay in the environment
(or the runtime model key for the OpenAI-compatible adapter), never in the saved
graph, and each vendor's key is only used for that vendor.

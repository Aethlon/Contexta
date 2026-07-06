# 18 — SDK-First Product Contract

This document is the source of truth for the public surface of contexta. It supersedes `04-api-contract.md` for product positioning: the API is an implementation detail, the SDK is the product.

The customer's request: *"the SDK should be the product."* That is the operating principle of this entire document.

## Decisions of record

1. **The SDK is the public product.** Marketing, docs, and quickstart all lead with SDK code, never curl.
2. **The HTTP API exists** so the SDK has something to call. It's documented for direct-integration fallback only.
3. **Pip and npm SDKs ship together.** Equal feature parity, equal docs surface.
4. **Twelve methods, no more.** The SDK surface is intentionally small. If a customer needs something we don't expose, that's a signal we should add it, not that they should call HTTP directly.
5. **Identical method names across Pip and npm.** Differences only where idiomatic (snake_case vs camelCase).
6. **Quiet defaults.** No required configuration beyond `CONTEXTA_API_KEY`.


## The twelve methods

```
observe                  ingest a conversation observation
observe_batch / observeBatch  same, multiple at once
context                  get a token-budgeted context bundle
retrieve                 lower-level: get ranked memories
explain                  explainability for one memory
delete                   permanently delete a memory
archive                  soft-hide a memory from retrieval
restore                  unhide an archived memory
pin                      protect a memory from decay
unpin                    release the pin
timeline                 chronological event log for a user
register_policy / registerPolicy   custom extraction policy
register_schema / registerSchema   custom structured memory schema
ping                     liveness check (used by SDKs internally and CLI)
```

That's thirteen if you count `ping`. Customer-relevant: twelve.

Anything not on this list is intentionally not in the SDK at v1. Examples of what's NOT in the SDK:

- `update_memory` — memories are not edited directly. Submit a new observation; the truth maintenance engine handles supersession.
- `get_memory` — exposed as `explain(memory_id).memory`. We don't want customers fetching memories one-at-a-time as if it's a CRUD store.
- `list_memories` — exposed as `retrieve(query="*", limit=N)` or `timeline(user_id)`. We don't want pagination over the entire memory store as a default flow.
- `create_session` — sessions auto-create on first observation. Manual session creation is rarely needed; available via raw HTTP for advanced cases.
- `register_project`, `create_api_key` — project and key management belongs to the dashboard, not the runtime SDK.

## Public shape (Python)

```python
from contexta_client import contexta, Asynccontexta

# Sync
m = contexta.from_env()
# or: m = contexta(api_key="mk_live_...", base_url="https://api.contexta.dev")

# Observe a conversation turn
m.observe(
    user_id="u_123",
    session_id="s_456",  # optional; if omitted, a session is auto-created
    messages=[
        {"role": "user", "content": "I prefer Postgres over Mongo for relational data."},
        {"role": "assistant", "content": "Got it."},
    ],
    metadata={"agent": "coding-agent", "version": "1.4"},
    policy="coding-agent",  # optional: applies a registered policy
)

# Get token-budgeted context for the next turn
ctx = m.context(
    user_id="u_123",
    session_id="s_456",
    query="what databases does the user prefer?",  # optional, improves ranking
    token_budget=1500,
    rerank=False,
)

# Inject into your LLM call
response = openai.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": ctx.to_system_prompt()},
        {"role": "user", "content": "..."},
    ],
)

# Lower-level retrieval if you want raw scored memories
memories = m.retrieve(
    user_id="u_123",
    query_text="postgresql preferences",
    memory_types=["preference", "fact"],
    tags=["database"],
    limit=20,
)

# Explainability for debugging
explanation = m.explain(memory_id="01J...")
print(explanation.scoring_breakdown)
print(explanation.extraction_source)

# Lifecycle ops
m.pin(memory_id)
m.archive(memory_id)
m.delete(memory_id)

# Timeline of a user's memory events
events = m.timeline(user_id="u_123", limit=50)

# Customizing extraction
m.register_policy(
    name="support-agent",
    store_rules=[{"memory_types": ["preference", "fact"]}],
    ignore_rules=[{"patterns": [r"^(thanks|hi|hello)\b"]}],
)

m.register_schema(
    name="InvoiceLineItem",
    fields=[
        {"name": "vendor", "type": "string", "required": True},
        {"name": "amount", "type": "number", "required": True},
        {"name": "currency", "type": "enum", "values": ["USD", "EUR"], "required": True},
    ],
)

# Async for high-throughput agents
am = Asynccontexta.from_env()
async def turn(user_msg: str):
    ctx = await am.context(user_id="u_123", session_id="s_456", token_budget=1500)
    # ... call LLM, get response ...
    await am.observe(user_id="u_123", session_id="s_456", messages=[...])
```

## Public shape (TypeScript / npm)

```ts
import { contexta, Asynccontexta } from "@contexta/client";

const contexta = contexta.fromEnv();
// or: new contexta({ apiKey: "mk_live_...", baseUrl: "https://api.contexta.dev" })

await contexta.observe({
  userId: "u_123",
  sessionId: "s_456",
  messages: [
    { role: "user", content: "I prefer Postgres over Mongo." },
    { role: "assistant", content: "Got it." },
  ],
  metadata: { agent: "coding-agent" },
  policy: "coding-agent",
});

const ctx = await contexta.context({
  userId: "u_123",
  sessionId: "s_456",
  query: "what databases does the user prefer?",
  tokenBudget: 1500,
});

// In your LLM call (OpenAI SDK example)
const response = await openai.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [
    { role: "system", content: ctx.toSystemPrompt() },
    { role: "user", content: "..." },
  ],
});

const memories = await contexta.retrieve({
  userId: "u_123",
  queryText: "postgresql preferences",
  memoryTypes: ["preference", "fact"],
  tags: ["database"],
  limit: 20,
});

const explanation = await contexta.explain(memoryId);

await contexta.pin(memoryId);
await contexta.archive(memoryId);
await contexta.delete(memoryId);

await contexta.registerPolicy({
  name: "support-agent",
  storeRules: [{ memoryTypes: ["preference", "fact"] }],
  ignoreRules: [{ patterns: ["^(thanks|hi|hello)\\b"] }],
});
```

The TypeScript SDK works in:

- Node 20+
- Vercel Edge Runtime
- Cloudflare Workers
- Bun, Deno
- Browser (with CORS, not the typical use case)

## Configuration

The SDK reads:

```env
CONTEXTA_API_KEY=mk_live_...           # required
CONTEXTA_API_URL=https://api.contexta.dev   # default, override for region or self-hosted-dev
CONTEXTA_TIMEOUT_MS=30000              # default
CONTEXTA_MAX_RETRIES=3                 # default
CONTEXTA_TELEMETRY=true                # default; set false to disable anonymized SDK telemetry
CONTEXTA_BUFFER_PATH=~/.contexta/buffer.jsonl  # local durable buffer for offline/network-fail
```

Or via constructor options for explicit configuration.

## What `Context` looks like

```python
@dataclass
class Context:
    user_profile: UserProfile | None
    active_projects: list[Project]
    preferences: list[Preference]
    goals: list[Goal]
    recent_events: list[Event]
    relevant_memories: list[ScoredMemory]
    token_usage: TokenUsage   # actual tokens used per section
    cache_hit: bool
    request_id: str
    
    def to_system_prompt(self, *, template: str | None = None) -> str:
        """Render context as a structured system prompt block. Default template included."""
    def to_messages(self) -> list[Message]:
        """Render as role/content pairs."""
    def to_markdown(self) -> str:
        """Render as markdown for debugging."""
    def to_dict(self) -> dict:
        """Raw JSON dict."""
```

The default `to_system_prompt()` produces a structured block agents can paste into any LLM call. Customers can override the template per call.


## Failure modes the SDK handles internally

The SDK shields the customer from operational failures unless they're truly unrecoverable.

### Auto-retried (transparent to caller)
- 5xx server errors (3 retries with exponential backoff: 1s, 2s, 4s).
- 429 rate-limited (honors `Retry-After`, retries up to 3 times).
- Connection refused / network errors (3 retries with backoff).
- DNS failure (3 retries with backoff).

### Buffered locally (transparent to caller)
- Persistent network failure (writes go to local durable buffer, replay on reconnect).
- Buffer auto-flushes on next successful API call.

### Surfaced as exceptions (caller must handle)
- 401 `AuthenticationError`: invalid or revoked API key.
- 403 `AuthorizationError`: scope insufficient or cross-tenant attempt.
- 404 `NotFoundError`: memory/session doesn't exist.
- 422 `ValidationError`: malformed request, with field-level details.
- 409 `ConflictError`: idempotency key collision with different body.
- 429 `QuotaExceededError`: hard cap engaged (after retry budget exhausted on rate limit).

### Reported to logs but not raised
- Telemetry post failure: log warning, never break customer code.
- Background buffer flush failure: log warning, retry on next call.

## Idempotency

SDKs auto-generate UUIDv7 idempotency keys for all writes. Customers don't have to think about it. They CAN supply one explicitly:

```python
m.observe(..., idempotency_key="my-stable-key")
```

Useful when the customer wants to dedupe based on their own stable identifier (e.g., a Slack message ID).

## Local durable buffer

When offline or during a contexta outage, writes are buffered to disk (or IndexedDB in browser):

```python
# Path: $HOME/.contexta/buffer.jsonl (or override via CONTEXTA_BUFFER_PATH)
# Rotates at 50 MB or 1000 entries
# Each line: {"endpoint": "/v1/observations", "body": {...}, "idempotency_key": "...", "created_at": "..."}
```

On any successful API call after recovery, buffer is flushed in batches of 50. If a write fails fatally (e.g., 422 because schema changed), it's moved to a dead-letter file (`~/.contexta/dead-letter.jsonl`) and the customer is shown a warning on next CLI use.

The buffer is opt-out:

```python
m = contexta(api_key=..., enable_buffer=False)
```

For environments where local disk is undesirable (Lambda functions, edge workers), the buffer is automatically disabled.

## Telemetry

Default-on, opt-out via `CONTEXTA_TELEMETRY=false` or constructor option.

We send (anonymized):
- SDK version, runtime version, OS family.
- Endpoints called (counts, status codes, durations).
- Error categories (no payloads, no IDs).

We never send:
- API keys (or any auth).
- User content (messages, queries).
- User IDs, organization IDs.

The data is used to detect SDK bugs (sudden 4xx spike), prioritize integrations, plan deprecations.

Documented in the SDK README and on the privacy page.

## Versioning

| Concept | Convention |
|---|---|
| SDK version | semver |
| API version | URL prefix `/v1/` |
| SDK 1.x | calls API v1 |
| SDK 2.x | calls API v2 |
| Breaking SDK change | major bump, 12-month deprecation runway |
| New optional method | minor bump |
| Bug fix | patch bump |

Pre-1.0 (during closed beta), we may bump major freely. After 1.0 (public launch), strict semver for 24 months minimum.

## Why we did NOT design SDK around raw endpoints

A common alternative: thin SDK that mirrors HTTP endpoint-by-endpoint (`contexta.observations.create(...)`, `contexta.memories.list(...)`).

We rejected this because:

1. Customers don't want to think about HTTP. They want "remember" and "recall."
2. The HTTP endpoints have ergonomic warts (e.g., context bundle is a GET with many query params; we want it to feel like a method call).
3. Action verbs (`observe`, `recall`) match the agent developer's mental model better than CRUD nouns.
4. Smaller surface = easier docs, faster onboarding, fewer footguns.

The internal HTTP contract (in `04-api-contract.md`) stays clean and complete. The SDK just maps the customer-facing actions to underlying HTTP calls. That mapping can change without breaking the SDK.

## Marketing line

> *"`contexta.observe()` to remember. `contexta.context()` to recall. The rest is implementation."*

That's the line. Two methods make a product real for an agent dev. Everything else is leverage on top.

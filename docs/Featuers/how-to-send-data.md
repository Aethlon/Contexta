# Sending Data to Contexta: Practical Ingestion Guide

How to get conversational turns, agent execution logs, and system events into Contexta so they are sanitized, extracted into durable memories, and indexed for hybrid retrieval.

---

## 1. Ingestion pathways

| Interface | Protocol / Port | Best for | Notes |
| :--- | :--- | :--- | :--- |
| **Python SDK** | HTTP client (`clients/python`) | Python agents (LangChain, LlamaIndex, custom loops) | `Contexta.observe()` |
| **TypeScript SDK** | HTTP client (`clients/typescript`) | Node, Next.js, Bun, Deno, edge runtimes | `Contexta.observe()` |
| **Core REST API** | `POST :8000/v1/observations` | Direct REST, webhooks, microservices | Requires an API key |
| **Go gateway** | `POST https://localhost:8443/v1/observations` | Only if you deliberately run `--profile edge` | Off by default; profile-gated |
| **MCP server** | `:8765/sse` | Cursor, Windsurf, Claude Desktop | `contexta_remember` tool |
| **Batch** | `POST :8000/v1/observations/batch` | Historical imports, benchmark seeding | Up to 100 per call |

Every path funnels into the same validated `ObservationPayload` schema and the same nine-stage pipeline.

---

## 2. The data contract: `ObservationPayload`

```json
{
  "user_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "organization_id": "96d29395-6d90-4ba2-9eed-6a851e0290c1",
  "session_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  "occurred_at": "2024-10-12T14:45:00-04:00",
  "observed_at": "2024-10-12T19:02:11Z",
  "timezone": "America/New_York",
  "source_id": "conversation-42",
  "message_id": "batch-7",
  "messages": [
    {
      "role": "user",
      "content": "I am moving to Seattle next month and adopting a golden retriever named Rusty.",
      "occurred_at": "2024-10-12T14:45:00-04:00",
      "message_id": "message-7"
    },
    {
      "role": "assistant",
      "content": "Congratulations on the move to Seattle! Have you found pet-friendly housing?"
    }
  ],
  "metadata": {"agent_id": "agent-orchestrator-01", "channel": "slack"}
}
```

### Fields

- `user_id` *(UUID, required)*: the end-user. **Must equal the actor bound to your API key**, or the route returns `403`.
- `organization_id` *(UUID, required)*: the tenant. Must equal the key's organization, or `403`.
- `session_id` *(UUID, required)*: conversation grouping. Create one with `POST /v1/sessions` or generate your own. The observation route does **not** auto-generate it.
- `messages` *(array, required)*: `{"role", "content"}` turns. `speaker` / `text` keys are accepted by the temporal normalizer but the extractor reads `role` / `content`.
- `occurred_at` *(datetime, optional)*: when the source event happened. The preferred reference for relative expressions.
- `observed_at` *(datetime, optional)*: when Contexta observed it. Fallback reference when `occurred_at` is absent.
- `timezone` *(IANA string, optional)*: required for correct day, weekday, and calendar-boundary resolution. Alias `event_timezone`.
- `temporal_precision` / `temporal_basis` *(string, optional)*: aliases `precision` and `basis`.
- `event_at`, `event_start`, `event_end` *(datetime, optional)*: an explicit event window.
- `source_id` / `message_id` / `source_message_id` *(any, optional)*: provenance, carried into `structured_data.temporal_source`.
- `source_start`, `source_end`, `source_span` *(int / object, optional)*: span within the source. `span` is accepted as an alias.
- `original_text`, `normalized_text` *(string, optional)*: redacted before they reach the LLM.
- `metadata` *(object, optional)*: opaque, attached to audit and telemetry.
- `policy` *(string, optional)*: recorded as an opaque string. **There is no policy registry** — `POST /v1/policies` does not exist.

Prefer structured timestamps over embedding a date marker in the message text. With no valid reference time, Contexta preserves expressions like `next month` as unknown rather than inventing a date.

Both SDKs now expose the temporal fields. The Python signature is
`observe(*, user_id, session_id=None, messages, metadata=None, policy=None, idempotency_key=None, occurred_at=None, observed_at=None, source_id=None, message_id=None, timezone=None)`
and the TypeScript `ObserveInput` carries `occurredAt`, `observedAt`, `sourceId`, `messageId`, and `timezone`.

---

## 3. REST

```bash
curl -X POST http://localhost:8000/v1/observations \
  -H "Authorization: Bearer $CONTEXTA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "'$CONTEXTA_ACTOR_ID'",
    "organization_id": "'$CONTEXTA_ORG_ID'",
    "session_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
    "occurred_at": "2024-10-12T14:45:00-04:00",
    "timezone": "America/New_York",
    "messages": [
      {"role": "user", "content": "I will start my masters in Clinical Psychology at UW in September 2025."}
    ],
    "metadata": {"source": "onboarding"}
  }'
```

Response:

```json
{
  "job_id": "e305e552-8da5-42cb-b7ff-cb54e3d939a8",
  "observation_id": "e305e552-8da5-42cb-b7ff-cb54e3d939a8",
  "status": "accepted"
}
```

The route commits the observation, its source turns, and an outbox event **before** returning this `202`. It does not return a synchronous memory count. Use `GET /v1/observations/{observation_id}` to inspect attempt, outbox, error, and completion state.

Keys are `mk_live_<url-safe>`, not `ctx_live_`. Send them as `Authorization: Bearer <key>` or `x-api-key: <key>`; identity headers are optional cross-checks that must agree with the key.

---

## 4. Python SDK

```bash
pip install -e clients/python
```

```python
from contexta_client import Contexta

memory = Contexta.from_env()

result = memory.observe(
    user_id=ACTOR_UUID,
    session_id="c9bf9e57-1685-4c89-bafb-ff5af830be8a",
    messages=[
        {"role": "user", "content": "I am lactose intolerant, so please avoid dairy recommendations."},
        {"role": "assistant", "content": "Noted! I'll only recommend dairy-free meals and recipes."},
    ],
    metadata={"platform": "web_chat"},
    idempotency_key="conversation-42-turn-1",
    occurred_at="2024-10-12T19:02:11Z",
    timezone="UTC",
)
print(result.job_id, result.status)
```

The canonical class is `Contexta`. The lowercase `contexta` still imports and works but emits a `DeprecationWarning`.

---

## 5. TypeScript SDK

```bash
npm install ./clients/typescript
```

```typescript
import { Contexta } from "@contexta/client";

const memory = Contexta.fromEnv();

await memory.observe({
  userId: ACTOR_UUID,
  organizationId: ORGANIZATION_ID,
  sessionId: "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  messages: [
    { role: "user", content: "I prefer working in Go and React." },
    { role: "assistant", content: "Great! I'll keep your stack preferences in mind." },
  ],
  occurredAt: "2024-10-12T19:02:11Z",
  timezone: "UTC",
});
```

`AsyncContexta` has the same surface for async callers. The lowercase `contexta` / `Asynccontexta` still work but log a single `console.warn`.

---

## 6. Batch and historical ingestion

`POST /v1/observations/batch` takes up to **100** observations, as a bare array or `{"observations": [...]}`. Invalid items are reported in `errors` with index-qualified field paths; valid items still ingest.

```python
from uuid import uuid4

for session in historical_sessions:
    messages = [
        {"role": turn["speaker"], "content": turn["text"]}
        for turn in session["turns"]
    ]
    memory.observe(
        user_id=user_id,
        session_id=str(uuid4()),
        messages=messages,
        occurred_at=session["started_at"],
        observed_at=import_timestamp,
        timezone="UTC",
        source_id=session["sample_id"],
    )
```

That is the shape the LoCoMo harness uses. Anchor every session explicitly rather than relying on ingestion time.

---

## 7. What happens under the hood

Every observation walks the same nine stages.

1. **Redact** — `contexta/core/extraction/sensitive_filter.py` scrubs API keys, JWTs, bearer tokens, passwords, OTPs, session cookies, and card numbers to `[REDACTED]`. **Fail-closed**: if the gate errors, the observation is rejected rather than forwarded unredacted.
2. **Contexta Cortex decision gate** — when Cortex routing is enabled, ephemeral chit-chat can be skipped before extraction and typed hints passed to the extractor. **Offline mode bypasses this entirely** rather than depending on an external routing service.
3. **Temporal grounding** — relative expressions are normalized only when a reference time exists. The basis and provenance are retained; unresolved expressions stay unknown.
4. **Structured extraction** — the extraction worker on `:8002` returns typed memory candidates with confidence and explicit temporal precision.
5. **Deduplication** — in-batch merge, then a check against the `fact_key` slot. A `subject`/`predicate`/`object` triple yields an `sfx1:<sha256>` slot key so a rephrasing lands in the same slot.
6. **Scoring** — importance from emphasis, decision impact, and mention count; confidence from source type. Low-value extractions drop out before they cost an embedding.
7. **Entity graph resolution** — named entities and typed relationship edges are resolved and written.
8. **Reconcile** — a contradicted fact is closed with `valid_to = now()` and its lineage recorded through `memory_version.superseded_by_id`. Enforced by the partial unique index `uq_memory_record_current_fact_slot`.
9. **Embed** — a local 1024-dimension `Qwen/Qwen3-Embedding-0.6B` vector, plus a `tsvector` search projection for lexical matching.

The stock HTTP route commits tenant-scoped observation records, source turns, and an outbox event before acknowledging, then schedules durable processing by identifier. Periodic outbox recovery discovers pending tenants, claims events with leases, and republishes identifier-only work; only broker monitoring and deployment-specific soak tests remain operational concerns.

---

## 8. Known rough edges

- **`docker-compose.yml` still defaults `CONTEXTA_INFERENCE_NUM_CTX` to 4096.** The extractor's prompts are ~8,281 tokens, and `inference_server.py` sends `num_ctx` per request, which overrides the model's own `num_ctx 16384`. Raise it or extraction silently degrades to the heuristic fallback. See the [upgrade guide](../../src/app/reference/upgrade-v1.5.mdx).
- **`policy` is recorded but never read.** There is no registry to register a policy into.
- **`session_id` is not auto-generated.** The old docs claimed it was; `ObservationPayload` marks it required.
- **The SDKs expose `sessionId`/`session_id` as optional** even though the route requires it, so omitting it fails at the server with a `422` rather than in the client.

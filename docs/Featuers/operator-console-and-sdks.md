# Operator Console & Agent SDKs

Contexta ships an operator console for inspection and debugging, plus two typed SDKs for agent integration.

---

## 1. Operator console (`dashboard/`)

Next.js 15, React 19, TailwindCSS 4, NextAuth v5.

### Features

- **Memory inspector** — browse, filter, and inspect memories with the full JSONB payload.
- **Interactive knowledge graph** — explore entity nodes and typed edges, click through to linked memories.
- **API key management** — issue and revoke keys scoped to one organization.
- **MCP client console** — exercise MCP tools from the browser.
- **Live observation ingest** — submit an observation and watch it through the pipeline.

### The auth switch

**The console runs without a sign-in by default.** `CONTEXTA_DASHBOARD_AUTH` defaults to `off`, because Contexta is a self-hosted, single-operator tool. Set it to `on` to restore the NextAuth v5 credentials flow.

The tenant resolves in this order:

1. the `contexta_tenant` cookie, which the operator sets in the UI
2. `CONTEXTA_DASHBOARD_ORG_ID` / `CONTEXTA_DASHBOARD_USER_ID`
3. `CONTEXTA_DASHBOARD_API_KEY`, by asking the API which organization that key belongs to

If nothing resolves, the console reports "unresolved" and its API calls go out unauthenticated — they get a `401` — rather than silently acting on some other organization's data. The operator can see and change the active tenant in the UI at any time.

`docker-compose.yml` passes both `CONTEXTA_DASHBOARD_AUTH` and `CONTEXTA_DASHBOARD_API_KEY` through to the container, so you do not have to paste a key into a form.

> **With auth off, the console must not be exposed to an untrusted network.** Anyone who can reach the dashboard port acts as whatever tenant it resolved.

There is no "rotate" action in the console or the API — `POST /v1/keys/{id}/rotate` does not exist. Issue a new key and revoke the old one.

---

## 2. Agent SDKs

Both SDKs are in this repository and install from source. Neither is on PyPI or npm yet.

### Python (`clients/python`)

```bash
pip install -e clients/python
```

```python
from contexta_client import Contexta

client = Contexta(api_key="mk_live_...", base_url="http://localhost:8000/v1")

# Ingest an observation
client.observe(
    user_id=ACTOR_UUID,
    session_id="33333333-3333-4333-8333-333333333333",
    messages=[
        {"role": "user", "content": "I am switching our primary database to PostgreSQL with pgvector."},
        {"role": "assistant", "content": "Got it! I will remember this database choice."},
    ],
)

# Assemble context for the next prompt
context = client.context(
    user_id=ACTOR_UUID,
    session_id="33333333-3333-4333-8333-333333333333",
    token_budget=1500,
)
print(context.to_system_prompt())
```

The class is `Contexta` and the package is `contexta_client`. There is no `ContextaClient`, and the distribution is not importable as `contexta`. `context()` has **no `query` parameter** — it takes `user_id`, `session_id`, and `organization_id`.

### TypeScript (`clients/typescript`)

```bash
npm install ./clients/typescript
```

```typescript
import { Contexta } from "@contexta/client";

const client = new Contexta({
  apiKey: process.env.CONTEXTA_API_KEY!,
  baseUrl: "http://localhost:8000/v1",
});

// Ingest
await client.observe({
  userId: ACTOR_UUID,
  sessionId: "33333333-3333-4333-8333-333333333333",
  messages: [
    { role: "user", content: "Our staging server is at staging.internal:8080" },
  ],
});

// Retrieve scored memories
const { results } = await client.retrieve({
  userId: ACTOR_UUID,
  organizationId: ORGANIZATION_ID,
  queryText: "Where is staging deployed?",
  limit: 3,
});
```

The package is `@contexta/client`, not `@contexta/sdk`. In TypeScript `userId`, `organizationId`, and `sessionId` are all required on `context()`.

### Both

- `Contexta` / `AsyncContexta` are canonical. The lowercase `contexta` / `Asynccontexta` still work but warn.
- `user_id` must equal the actor bound to the API key, or the context fetch returns `403`.
- Writes carry an `Idempotency-Key`, retry with backoff, and queue to disk when the network is down. `flush()` drains, `close()` releases.

---

## 3. Feedback loop

The live route is `POST /v1/memories/{id}/feedback`:

```json
{"signal": "negative", "user_correction": "…", "penalty": 0.5}
```

It mutates `memory_record.utility_score` and `confidence` in place, which feeds the fusion quality prior on subsequent retrievals.

**There is no `GET /api/v1/feedback`.** That path was never real; the old documentation of it was wrong. The `retrieval_feedback` table it referred to was dropped in revision `020` because no code read it — the live path writes to `memory_record` directly.

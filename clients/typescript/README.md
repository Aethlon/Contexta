# @contexta/client

TypeScript SDK for contexta — persistent memory for AI agents.

## Installation

```bash
npm install @contexta/client
# or
pnpm add @contexta/client
# or
yarn add @contexta/client
```

## Quick Start

```typescript
import { Contexta } from "@contexta/client";

const memory = Contexta.fromEnv();

try {
  // Observe a conversation
  const { jobId } = await memory.observe({
    userId: "user_abc",
    organizationId: "org_xyz",
    sessionId: "session_123",
    messages: [
      { role: "user", content: "My name is Alice" },
      { role: "assistant", content: "Nice to meet you, Alice!" },
    ],
  });

  // Retrieve memories
  const { results } = await memory.retrieve({
    userId: "user_abc",
    organizationId: "org_xyz",
    queryText: "What is my name?",
  });

  // Build context for an LLM
  const ctx = await memory.context({
    userId: "user_abc",
    organizationId: "org_xyz",
    sessionId: "session_123",
  });
  console.log(ctx.toSystemPrompt());
} finally {
  memory.close();
}
```

`Contexta` and `AsyncContexta` are the canonical class names. The historical
lowercase `contexta` / `Asynccontexta` still import and work, but log a single
`console.warn` and will be removed in a future major release.

## Configuration

| Option           | Env Variable              | Default                   | Description                          |
|------------------|---------------------------|---------------------------|--------------------------------------|
| `apiKey`         | `CONTEXTA_API_KEY`        | —                         | API key (required)                   |
| `baseUrl`        | `CONTEXTA_API_URL`        | `https://api.contexta.dev`| API base URL (include `/v1`)         |
| `timeout`        | `CONTEXTA_TIMEOUT`        | `30000`                   | Request timeout (ms)                 |
| `maxRetries`     | `CONTEXTA_MAX_RETRIES`    | `3`                       | Max retry attempts                   |
| `telemetry`      | `CONTEXTA_TELEMETRY`      | `true`                    | Send SDK version headers             |
| `organizationId` | `CONTEXTA_ORGANIZATION_ID`| —                         | Required by `context()`/`createSession()` |
| `tls`            | `CONTEXTA_CA_BUNDLE`, `CONTEXTA_VERIFY_TLS` | verified | TLS trust configuration   |
| `dispatcher`     | —                         | —                         | Pre-built `undici.Agent` (Node)      |
| `fetch`          | —                         | global `fetch`            | Custom TLS-configured `fetch`        |

## TLS

Certificate verification is on by default. To trust the self-signed local
gateway, supply a CA bundle:

```typescript
const memory = new Contexta({
  apiKey: process.env.CONTEXTA_API_KEY!,
  tls: { caPath: "./certs/gateway-ca.pem" },   // or tls: { ca: "<PEM string>" }
});
```

Disabling verification is an explicit opt-in, never implicit, and logs a
one-time warning:

```typescript
const memory = new Contexta({ apiKey, tls: { rejectUnauthorized: false } });
```

Custom TLS options need a `dispatcher` built from `undici` (an optional peer
dependency) on Node. Anywhere `undici` is unavailable — or when you already have
a TLS-configured `fetch` — pass `fetch` instead; the SDK will use it as-is.

## Durability

Every write carries an `Idempotency-Key`, retries network failures with backoff,
and falls back to a durable on-disk queue when the network is down.

```typescript
const replayed = await memory.flush(); // drains the offline queue
memory.close();                        // safe to call twice
```

`withContexta()` is the equivalent of Python's `with Contexta(...)` block:

```typescript
import { withContexta } from "@contexta/client";

const systemPrompt = await withContexta({ apiKey }, async (memory) => {
  const ctx = await memory.context({ userId, organizationId, sessionId });
  return ctx.toSystemPrompt();
});
```

## API

### `Contexta.observe(input)`
Submit a conversation for memory extraction. Returns `{ jobId, status }`.

### `Contexta.observeBatch(inputs)`
Submit multiple conversations at once. Returns `{ jobs, status }`.

### `Contexta.retrieve(input)`
Search memories by semantic similarity, keywords, and graph traversal. Returns scored results.

### `Contexta.retrieveBatch(queries)`
Run several `retrieve` queries in one round trip. Returns `{ query, count, results }` entries.

### `Contexta.investigate(input)`
Iterative agentic multi-hop investigation. Returns an `InvestigateResult` with the investigation trace.

### `Contexta.search(input)` / `Contexta.hybrid(input)`
Pure vector search and multi-signal hybrid search.

### `Contexta.context(input)`
Get assembled context for an LLM prompt. Hits `GET /v1/memories/context`, which
requires `userId`, `organizationId` and `sessionId`. Returns a `ContextResult` with helper methods:
- `toSystemPrompt()` — formatted system prompt string
- `toMessages()` — array of `{ role, content }` messages
- `toMarkdown()` — markdown formatted context
- `toDict()` — raw context object

### `Contexta.explain(memoryId)`
Get scoring breakdown and supersession history for a memory.

### `Contexta.feedback(memoryId, input)`
Send `positive` / `negative` feedback to adjust utility and contradiction scoring.

### `Contexta.addRule(input)`
Store a decay-exempt behavioural directive. Implemented on top of `observe`.

### `Contexta.reflect(input)`
Run autonomous reflection: detect contradictions, resolve supersessions, consolidate patterns.

### `Contexta.pin(memoryId)` / `Contexta.unpin(memoryId)`
Pin or unpin a memory to control decay behavior.

### `Contexta.archive(memoryId)` / `Contexta.restore(memoryId)`
Archive or restore a memory.

### `Contexta.delete(memoryId)`
Permanently delete a memory.

### `Contexta.timeline(userId)`
Get chronological event history for a user.

### `Contexta.getMemory(memoryId)`
Get full details for a single memory.

### `Contexta.getMany(memoryIds)`
Batch fetch memory records by ID.

### `Contexta.listMemories(options?)`
List memories with optional filters (userId, memoryType, state, pinned, archived, offset, limit).

### `Contexta.traverse(input)`
Multi-hop entity graph traversal from a root entity.

### `Contexta.ping()`
Health check against the service root. Returns `{ status, version }`.

### `Contexta.createSession(input)` / `Contexta.endSession(sessionId)` / `Contexta.getSession(sessionId)`
Manage conversation sessions.

### `Contexta.registerPolicy(input)` / `Contexta.listPolicies()`
Manage extraction policies.

### `Contexta.registerSchema(input)`
Register a memory schema.

## API parity

The Python and TypeScript clients expose an identical set of 32 public methods.
The canonical list lives in [`../public-api.manifest.json`](../public-api.manifest.json)
and is asserted by both test suites, so the SDKs cannot drift apart silently.

## Environments

Works in Node.js 18+, Vercel Edge Runtime, Cloudflare Workers, Bun, Deno, and modern browsers. Zero required external dependencies — uses native `fetch`, `crypto`, and `AbortSignal.timeout`. `undici` is an optional peer dependency used only for custom TLS configuration.

## License

MIT

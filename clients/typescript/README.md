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
import { contexta } from "@contexta/client";

const contexta = contexta.fromEnv();

// Observe a conversation
const { jobId } = await contexta.observe({
  userId: "user_abc",
  organizationId: "org_xyz",
  sessionId: "session_123",
  messages: [
    { role: "user", content: "My name is Alice" },
    { role: "assistant", content: "Nice to meet you, Alice!" },
  ],
});

// Retrieve memories
const { results } = await contexta.retrieve({
  userId: "user_abc",
  organizationId: "org_xyz",
  queryText: "What is my name?",
});

// Build context for an LLM
const ctx = await contexta.context({
  userId: "user_abc",
  organizationId: "org_xyz",
  sessionId: "session_123",
});
console.log(ctx.toSystemPrompt());
```

## Configuration

| Option       | Env Variable        | Default                    | Description                |
|-------------|---------------------|----------------------------|----------------------------|
| `apiKey`    | `CONTEXTA_API_KEY`   | —                          | API key (required)         |
| `baseUrl`   | `CONTEXTA_API_URL`   | `https://api.contexta.dev`  | API base URL               |
| `timeout`   | `CONTEXTA_TIMEOUT`   | `30000`                    | Request timeout (ms)       |
| `maxRetries`| `CONTEXTA_MAX_RETRIES`| `3`                       | Max retry attempts         |
| `telemetry` | `CONTEXTA_TELEMETRY` | `true`                     | Send SDK version headers   |

## API

### `contexta.observe(input)`
Submit a conversation for memory extraction. Returns `{ jobId, status }`.

### `contexta.observeBatch(inputs)`
Submit multiple conversations at once. Returns `{ jobs, status }`.

### `contexta.retrieve(input)`
Search memories by semantic similarity, keywords, and graph traversal. Returns scored results.

### `contexta.context(input)`
Get assembled context for an LLM prompt. Returns a `ContextResult` with helper methods:
- `toSystemPrompt()` — formatted system prompt string
- `toMessages()` — array of `{ role, content }` messages
- `toMarkdown()` — markdown formatted context
- `toDict()` — raw context object

### `contexta.explain(memoryId)`
Get scoring breakdown and supersession history for a memory.

### `contexta.pin(memoryId)` / `contexta.unpin(memoryId)`
Pin or unpin a memory to control decay behavior.

### `contexta.archive(memoryId)` / `contexta.restore(memoryId)`
Archive or restore a memory.

### `contexta.delete(memoryId)`
Permanently delete a memory.

### `contexta.timeline(userId)`
Get chronological event history for a user.

### `contexta.getMemory(memoryId)`
Get full details for a single memory.

### `contexta.listMemories(options?)`
List memories with optional filters (userId, memoryType, state, pinned, archived, offset, limit).

### `contexta.ping()`
Health check. Returns `{ status, version }`.

### `contexta.createSession(input)` / `contexta.endSession(sessionId)` / `contexta.getSession(sessionId)`
Manage conversation sessions.

### `contexta.registerPolicy(input)` / `contexta.listPolicies()`
Manage extraction policies.

### `contexta.registerSchema(input)`
Register a memory schema.

## Environments

Works in Node.js 18+, Vercel Edge Runtime, Cloudflare Workers, Bun, Deno, and modern browsers. Zero external dependencies — uses native `fetch`, `crypto`, and `AbortSignal.timeout`.

## License

MIT

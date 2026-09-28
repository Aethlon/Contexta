import type { DocContext, DocSection } from "./docs-content";
import { mcpConfigJson } from "./mcp-reference";

/**
 * Every value here is interpolated from live tenant state, so the docs cannot
 * quietly drift away from the running system — the extractor name, the
 * embedding dimensions and the MCP tool list all come from the API.
 */
export function buildSections(ctx: DocContext): DocSection[] {
  const key = ctx.keyPrefix ? `${ctx.keyPrefix}...` : "<your API key>";

  return [
    {
      id: "overview",
      title: "Overview",
      blurb: "What Contexta does, and which three models are doing the work.",
      blocks: [
        {
          kind: "prose",
          text: "Contexta is a memory layer for agents. You hand it conversation turns; it extracts discrete, typed facts, links them into a knowledge graph, embeds them locally, and later hands back a token-budgeted slice of what is relevant to the current question.",
        },
        {
          kind: "table",
          head: ["Stage", "Model", "Status"],
          rows: [
            ["Extraction", ctx.engine.extractionModel, ctx.engine.extractionStatus],
            ["Embedding", `${ctx.engine.embeddingModel} · ${ctx.engine.dimensions}-d`, ctx.engine.embeddingProfile],
            ["Reranking", ctx.engine.rerankerModel, "local"],
          ],
        },
        {
          kind: "note",
          tone: "info",
          title: "Everything above runs locally",
          text: "No data leaves this machine. The extractor is a fine-tune of LiquidAI/LFM2.5 served through Ollama; embedding and reranking are local Qwen3 models. No cloud API key is involved.",
        },
        {
          kind: "prose",
          text: "Contradictions are resolved rather than accumulated: when a fact is corrected, the old row is closed with a validity window and linked to its replacement, so a stale belief never competes with the current one.",
        },
      ],
    },

    {
      id: "getting-started",
      title: "Getting started",
      blurb: "Mint a key, send one observation, read one memory back.",
      blocks: [
        {
          kind: "prose",
          text: "If you have not created a key yet, do it from the MCP page — it mints one in place and verifies the connection in the same step.",
        },
        {
          kind: "code",
          label: "Send an observation",
          lang: "bash",
          code: `curl -X POST ${ctx.apiUrl}/v1/observations \\
  -H "x-api-key: ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "user_id": "${ctx.userId}",
    "organization_id": "${ctx.orgId}",
    "session_id": "33333333-3333-4333-8333-333333333333",
    "messages": [
      {"role": "user", "content": "I moved to London; my port is 5432."}
    ]
  }'`,
        },
        {
          kind: "note",
          tone: "info",
          title: "202, not 200",
          text: "Extraction is asynchronous. The response returns a job id immediately; poll it and then retrieve.",
        },
        {
          kind: "code",
          label: "Read it back",
          lang: "bash",
          code: `curl -X POST ${ctx.apiUrl}/v1/retrieve \\
  -H "x-api-key: ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "query_text": "Where do I live?",
    "user_id": "${ctx.userId}"
  }'`,
        },
      ],
    },

    {
      id: "account",
      title: "Your account",
      blurb: "One key means one organization and one actor. That pairing is enforced.",
      blocks: [
        {
          kind: "table",
          head: ["Value", "Yours"],
          rows: [
            ["Organization", ctx.orgId || "(unresolved)"],
            ["Actor / user_id", ctx.userId || "(unresolved)"],
            ["Key prefix", ctx.keyPrefix ?? "(no keys yet)"],
            ["API base", ctx.apiUrl],
          ],
        },
        {
          kind: "note",
          tone: "warn",
          title: "user_id must match the key's actor",
          text: "Every request's user_id has to equal the actor bound to the API key. A mismatch returns 403 rather than an empty result, which is deliberate — a silent empty list is far harder to debug than an error.",
        },
        {
          kind: "prose",
          text: "Only a SHA-256 hash and a short display prefix are stored, so an existing key cannot be shown again. That is why the snippets above show a prefix; copy a real key from the MCP page when you create one.",
        },
        {
          kind: "list",
          items: [
            "Either header works: x-api-key, or Authorization: Bearer.",
            "Organization and actor headers are optional cross-checks, not the primary proof.",
            "Keys are scoped read+write and revocable individually.",
          ],
        },
      ],
    },

    {
      id: "rest-api",
      title: "REST API",
      blurb: "The endpoints you are most likely to need.",
      blocks: [
        {
          kind: "table",
          head: ["Method", "Path", "Purpose"],
          rows: [
            ["POST", "/v1/observations", "Submit a conversation for extraction"],
            ["POST", "/v1/observations/batch", "Submit several at once"],
            ["GET", "/v1/observations/{id}", "Poll an extraction job"],
            ["POST", "/v1/retrieve", "Hybrid retrieval: dense + lexical + graph"],
            ["GET", "/v1/memories", "List memories for your organization"],
            ["GET", "/v1/memories/{id}/explain", "Scoring breakdown and lineage"],
            ["GET", "/v1/entities/graph/{user_id}", "Entity graph for a user"],
            ["GET", "/v1/graph/traverse", "Multi-hop traversal"],
            ["GET", "/v1/audit", "Tenant-scoped audit log"],
            ["GET", "/v1/system/engine-status", "Model telemetry, including the extractor"],
            ["GET", "/v1/keys", "List API keys"],
            ["POST", "/v1/keys", "Create a key — the token is returned once"],
            ["DELETE", "/v1/keys/{id}", "Revoke a key"],
          ],
        },
        {
          kind: "prose",
          text: "The full machine-readable contract is served at /openapi.json on the same base URL.",
        },
      ],
    },

    {
      id: "python",
      title: "Python SDK",
      blurb: "Typed client with retries, idempotency and an offline queue.",
      blocks: [
        {
          kind: "code",
          label: "Install",
          lang: "bash",
          code: "pip install contexta-client",
        },
        {
          kind: "code",
          label: "Use",
          lang: "python",
          code: `from contexta_client import Contexta

client = Contexta(
    api_url="${ctx.apiUrl}",
    api_key="${key}",
)

client.observe(
    user_id="${ctx.userId}",
    organization_id="${ctx.orgId}",
    messages=[{"role": "user", "content": "I prefer Python and dark mode."}],
)

result = client.retrieve(
    user_id="${ctx.userId}",
    organization_id="${ctx.orgId}",
    query_text="What are the user's preferences?",
)
print(result)`,
        },
        {
          kind: "list",
          items: [
            "Writes carry an Idempotency-Key, so a retry cannot duplicate a memory.",
            "429, 5xx and network errors are retried with backoff.",
            "If the network drops, writes queue on disk. flush() drains, close() releases.",
          ],
        },
      ],
    },

    {
      id: "typescript",
      title: "TypeScript SDK",
      blurb: "Same client surface, with no required dependencies.",
      blocks: [
        {
          kind: "code",
          label: "Install",
          lang: "bash",
          code: "npm install contexta-client",
        },
        {
          kind: "code",
          label: "Use",
          lang: "ts",
          code: `import { Contexta } from "contexta-client";

const contexta = new Contexta({
  apiUrl: "${ctx.apiUrl}",
  apiKey: "${key}",
});

await contexta.observe({
  userId: "${ctx.userId}",
  organizationId: "${ctx.orgId}",
  messages: [{ role: "user", content: "I prefer dark mode and use Rust." }],
});

const { results } = await contexta.retrieve({
  userId: "${ctx.userId}",
  organizationId: "${ctx.orgId}",
  query: "user preferences",
});`,
        },
        {
          kind: "prose",
          text: "Runs on Node 18+, Bun, Deno, Vercel Edge and Cloudflare Workers using native fetch, crypto and AbortSignal.timeout — no polyfills, no mandatory packages.",
        },
      ],
    },

    {
      id: "mcp",
      title: "MCP",
      blurb: "Connect any MCP client directly to this memory store.",
      blocks: [
        {
          kind: "prose",
          text: `The server speaks streamable HTTP on ${ctx.mcpUrl} and requires an API key. It refuses to start without one rather than coming up unauthenticated.`,
        },
        {
          kind: "code",
          label: "Claude Code",
          lang: "bash",
          code: `claude mcp add contexta ${ctx.mcpUrl} --header "x-api-key: ${key}"`,
        },
        {
          kind: "code",
          label: "Any client — paste into its MCP config",
          lang: "json",
          code: mcpConfigJson(key),
        },
        {
          kind: "table",
          head: ["Tool", "Required", "Optional"],
          rows: ctx.tools.map((t) => [
            t.name,
            t.required.join(", ") || "—",
            t.optional.join(", ") || "—",
          ]),
        },
        {
          kind: "note",
          tone: "warn",
          title: "Never expose this port unauthenticated",
          text: "Every caller is scoped to its own key's tenant, but the port itself has no TLS. Terminate TLS in front of it if it is reachable from a network you do not control.",
        },
      ],
    },

    {
      id: "retrieval",
      title: "How retrieval works",
      blurb: "Three channels, one ordering.",
      blocks: [
        {
          kind: "prose",
          text: "Vector search misses the port number. Keyword search misses the intent. Graph traversal misses nothing, but only if it is bounded. Contexta runs all three and fuses the candidate pools.",
        },
        {
          kind: "list",
          items: [
            `Dense: cosine similarity over pgvector HNSW, ${ctx.engine.embeddingModel} at ${ctx.engine.dimensions} dimensions.`,
            "Lexical: a real GIN tsvector predicate for exact identifiers — ports, UUIDs, names.",
            "Graph: a single capped recursive CTE for typed multi-hop traversal.",
            "Fusion: weighted Reciprocal Rank Fusion, then a local cross-encoder rerank.",
            "Only currently-true facts are returned; superseded rows are excluded.",
          ],
        },
        {
          kind: "prose",
          text: "Every hit can explain itself: GET /v1/memories/{id}/explain returns the per-channel scores, the fact triple, the validity window and the supersession chain.",
        },
      ],
    },

    {
      id: "operations",
      title: "Operations",
      blurb: "Running it, and what to do when something looks wrong.",
      blocks: [
        {
          kind: "prose",
          text: "The whole stack is Docker Compose. bun and npm both work for the console; both lockfiles are committed.",
        },
        {
          kind: "code",
          label: "Common commands",
          lang: "bash",
          code: `docker compose up -d          # start
docker compose ps           # health of every service
docker compose logs -f worker
cd dashboard && npm run dev   # or: bun run dev`,
        },
        {
          kind: "table",
          head: ["Symptom", "Cause", "Fix"],
          rows: [
            [
              "Observations queue but no memories appear",
              "The local extraction model is down. Ollama runs on the host, not in Compose.",
              "Start Ollama, then confirm the Extractor row in the engine popover reads ready.",
            ],
            [
              "401 invalid_api_key",
              "Missing, revoked, or wrong key.",
              "Mint a fresh key from the MCP page.",
            ],
            [
              "403 on a request that looks valid",
              "user_id does not match the key's actor.",
              "Use the actor id bound to that key.",
            ],
            [
              "MCP status reads offline in Docker",
              "Fixed in v1.5; ensure CONTEXTA_MCP_URL is set for the console.",
              "It should resolve to http://mcp:8765, not localhost.",
            ],
            [
              "Server Action not found in the console",
              "The browser tab predates the current build.",
              "Hard refresh — action ids are hashed per build.",
            ],
          ],
        },
      ],
    },
  ];
}

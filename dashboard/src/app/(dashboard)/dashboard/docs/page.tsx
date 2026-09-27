import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { resolveOperatorIdentity } from "@/lib/dashboard-identity";
import { listApiKeysAction } from "@/app/actions";
import { Tabs } from "@/components/ui/tabs";
import { CopyButton } from "./copy-button";

export default async function DocsPage() {
  const identity = await resolveOperatorIdentity();
  const keys = await listApiKeysAction();
  const latestKey = Array.isArray(keys) && keys.length > 0 ? keys[0] : null;

  const userId = identity.userId ?? "";
  const orgId = identity.orgId ?? "";
  const apiUrl = process.env.CONTEXTA_API_URL ?? "http://localhost:8000";

  const envVars = `CONTEXTA_API_URL=${apiUrl}
CONTEXTA_API_KEY=${latestKey?.prefix ?? "mk_live_"}...`;

  const curlObserve = `curl ${apiUrl}/v1/observations \\
  -H "Authorization: Bearer $CONTEXTA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "user_id": "${userId}",
    "organization_id": "${orgId}",
    "session_id": "'$(uuidgen)'",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Remember I prefer Python and dark mode."},
      {"role": "assistant", "content": "Got it. I will remember your preferences."}
    ]
  }'`;

  const curlRetrieve = `curl -X POST ${apiUrl}/v1/retrieve \\
  -H "Authorization: Bearer $CONTEXTA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "user_id": "${userId}",
    "organization_id": "${orgId}",
    "query_text": "What are the user preferences?"
  }'`;

  const pythonSdk = `from contexta_client import Contexta

client = Contexta(
    api_url="${apiUrl}",
    api_key="${latestKey?.prefix ?? "mk_live_"}..."
)

# Submit an observation
client.observe(
    user_id="${userId}",
    organization_id="${orgId}",
    messages=[
        {"role": "user", "content": "I prefer Python and dark mode."},
        {"role": "assistant", "content": "Got it!"}
    ]
)

# Retrieve context
ctx = client.context(
    user_id="${userId}",
    query="What are the user preferences?",
    token_budget=1500
)`;

  const jsCode = `import { Contexta } from "contexta-client";

const contexta = new Contexta({
  apiUrl: "${apiUrl}",
  apiKey: "${latestKey?.prefix ?? "mk_live_"}...",
});

// Submit an observation
await contexta.observe({
  userId: "${userId}",
  organizationId: "${orgId}",
  messages: [
    { role: "user", content: "I prefer dark mode and use Rust." },
    { role: "assistant", content: "Noted!" }
  ],
});

// Retrieve context
const memories = await contexta.retrieve({
  userId: "${userId}",
  organizationId: "${orgId}",
  query: "user preferences",
});`;

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-fade-in font-mono text-xs pb-12">
      {/* Welcome Header */}
      <div className="border-b border-border pb-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <Badge>Setup</Badge>
            <h2 className="mt-3 text-2xl font-normal tracking-tight text-foreground">Agent Integration Guide</h2>
            <p className="mt-1 text-xs text-muted-foreground font-sans max-w-xl">
              Integrate Contexta into your agent or application. All IDs and endpoints below are pre-filled from the organization this console is currently acting on.
            </p>
          </div>
          <a
            href="/dashboard/mcp"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30 tone-green hover:bg-emerald-500/20 text-xs transition-colors self-start sm:self-auto"
          >
            <span>Model Context Protocol (MCP) &rarr;</span>
          </a>
        </div>
      </div>

      {!latestKey ? (
        <div className="flex items-start gap-3 border border-amber-500/30 bg-amber-500/10 p-4 rounded-lg tone-amber text-xs">
          <span>
            No API key found. <a href="/dashboard/api-keys" className="underline font-normal text-foreground">Create an API key</a> to see your personalized credentials.
          </span>
        </div>
      ) : null}

      {/* Account Info Cards */}
      <div className="grid gap-6 md:grid-cols-4">
        {[
          { label: "Org ID", value: orgId?.slice(0, 18) + "â€¦" },
          { label: "User ID", value: userId?.slice(0, 18) + "â€¦" },
          { label: "API Key", value: (latestKey?.prefix ?? "â€”") + "â€¦" },
          { label: "API URL", value: apiUrl },
        ].map((item) => (
          <Card key={item.label}>
            <CardContent className="p-4 space-y-1">
              <p className="text-[10px] font-mono tracking-widest uppercase text-[var(--text-secondary)]">{item.label}</p>
              <code className="block truncate font-mono text-xs text-[var(--foreground)]">{item.value}</code>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* SDK Documentation Tabs */}
      <Tabs
        tabs={[
          {
            label: "cURL",
            content: (
              <div className="space-y-6">
                <Card>
                  <CardHeader>
                    <CardTitle>1. Environment Variables</CardTitle>
                    <CardDescription>Set these in your shell or .env file.</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="relative">
                      <pre className="overflow-x-auto rounded-lg bg-[var(--background)] p-4 font-mono text-xs text-[var(--text-secondary)] border border-[var(--border)]/30 leading-relaxed">{envVars}</pre>
                      <CopyButton text={envVars} />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle>2. Send Observations</CardTitle>
                    <CardDescription>Submit conversations for memory extraction via the LLM pipeline.</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="relative">
                      <pre className="overflow-x-auto rounded-lg bg-[var(--background)] p-4 font-mono text-xs text-[var(--text-secondary)] border border-[var(--border)]/30 leading-relaxed">{curlObserve}</pre>
                      <CopyButton text={curlObserve} />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle>3. Retrieve Context</CardTitle>
                    <CardDescription>Get relevance-ranked memories for your agent.</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="relative">
                      <pre className="overflow-x-auto rounded-lg bg-[var(--background)] p-4 font-mono text-xs text-[var(--text-secondary)] border border-[var(--border)]/30 leading-relaxed">{curlRetrieve}</pre>
                      <CopyButton text={curlRetrieve} />
                    </div>
                  </CardContent>
                </Card>
              </div>
            ),
          },
          {
            label: "Python",
            content: (
              <Card>
                <CardHeader>
                  <CardTitle>Python SDK</CardTitle>
                  <CardDescription>
                    Install: <code className="rounded-md bg-[var(--background)] border border-[var(--border)]/30 px-2 py-1 font-mono text-xs text-[var(--foreground)] ml-1.5">pip install contexta-client</code>
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="relative">
                    <pre className="overflow-x-auto rounded-lg bg-[var(--background)] p-4 font-mono text-xs text-[var(--text-secondary)] border border-[var(--border)]/30 leading-relaxed">{pythonSdk}</pre>
                    <CopyButton text={pythonSdk} />
                  </div>
                </CardContent>
              </Card>
            ),
          },
          {
            label: "JavaScript",
            content: (
              <Card>
                <CardHeader>
                  <CardTitle>TypeScript / JavaScript</CardTitle>
                  <CardDescription>
                    Install: <code className="rounded-md bg-[var(--background)] border border-[var(--border)]/30 px-2 py-1 font-mono text-xs text-[var(--foreground)] ml-1.5">npm install contexta-client</code>
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="relative">
                    <pre className="overflow-x-auto rounded-lg bg-[var(--background)] p-4 font-mono text-xs text-[var(--text-secondary)] border border-[var(--border)]/30 leading-relaxed">{jsCode}</pre>
                    <CopyButton text={jsCode} />
                  </div>
                </CardContent>
              </Card>
            ),
          },
          {
            label: "MCP Server",
            content: (
              <div className="space-y-6">
                <Card>
                  <CardHeader>
                    <CardTitle>Model Context Protocol (MCP) Integration</CardTitle>
                    <CardDescription>
                      Connect Claude Desktop, Cursor, and Windsurf directly to your sovereign Contexta memory engine.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4 font-mono text-xs">
                    <div>
                      <p className="text-foreground font-medium mb-1">Option A: Server-Sent Events (SSE) Transport (Port :8765)</p>
                      <p className="text-[11px] text-muted-foreground mb-2">
                        Fastest setup when running via Docker Compose (the MCP container runs on :8765).
                      </p>
                      <div className="relative">
                        <pre className="overflow-x-auto rounded-lg bg-[var(--background)] p-4 font-mono text-xs text-[var(--text-secondary)] border border-[var(--border)]/30 leading-relaxed">{`{
  "mcpServers": {
    "contexta": {
      "url": "http://localhost:8765/sse"
    }
  }
}`}</pre>
                        <CopyButton text={`{\n  "mcpServers": {\n    "contexta": {\n      "url": "http://localhost:8765/sse"\n    }\n  }\n}`} />
                      </div>
                    </div>

                    <div>
                      <p className="text-foreground font-medium mb-1">Option B: Local Stdio Command (Claude Desktop / Cursor)</p>
                      <p className="text-[11px] text-muted-foreground mb-2">
                        Launch directly as a subprocess using your local Python environment:
                      </p>
                      <div className="relative">
                        <pre className="overflow-x-auto rounded-lg bg-[var(--background)] p-4 font-mono text-xs text-[var(--text-secondary)] border border-[var(--border)]/30 leading-relaxed">{`{
  "mcpServers": {
    "contexta": {
      "command": "python",
      "args": ["-m", "contexta.mcp"],
      "env": {
        "CONTEXTA_DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/contexta",
        "CONTEXTA_LOCAL_MODEL_SERVER_URL": "http://localhost:8001"
      }
    }
  }
}`}</pre>
                        <CopyButton text={`{\n  "mcpServers": {\n    "contexta": {\n      "command": "python",\n      "args": ["-m", "contexta.mcp"],\n      "env": {\n        "CONTEXTA_DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/contexta",\n        "CONTEXTA_LOCAL_MODEL_SERVER_URL": "http://localhost:8001"\n      }\n    }\n  }\n}`} />
                      </div>
                    </div>

                    <div className="rounded-lg border border-border bg-secondary/30 p-3 space-y-2">
                      <p className="font-semibold text-foreground">Exposed Autonomous Memory Tools:</p>
                      <ul className="space-y-1 text-[11px] text-muted-foreground list-disc list-inside">
                        <li><code className="text-foreground">contexta_remember(content, user_id, title, memory_type)</code>: Stores facts after redaction and extraction</li>
                        <li><code className="text-foreground">contexta_batch_remember(memories)</code>: Queues several memories and returns a job id</li>
                        <li><code className="text-foreground">contexta_recall(query, user_id, limit, graph_depth)</code>: 3-Layer hybrid recall (vector + lexical + graph, RRF fused, reranked)</li>
                        <li><code className="text-foreground">contexta_get_context(user_id, focus, max_memories)</code>: Token-budgeted context package</li>
                        <li><code className="text-foreground">contexta_forget(memory_id, reason)</code>: Closes the validity window of a memory and links its successor</li>
                        <li><code className="text-foreground">contexta_explore_graph(entity_name, user_id)</code>: Multi-hop graph traversal</li>
                        <li><code className="text-foreground">contexta_job_status(job_id)</code>: Polls an asynchronous remember job</li>
                        <li><code className="text-foreground">contexta_metrics()</code>: Engine counters for the calling tenant</li>
                      </ul>
                    </div>
                  </CardContent>
                </Card>
              </div>
            ),
          },
        ]}
      />

      {/* API Reference Table */}
      <Card>
        <CardHeader>
          <CardTitle>API Reference</CardTitle>
          <CardDescription>All available endpoints.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)]/30 text-left">
                  <th className="pb-3 pr-4 text-[10px] font-mono tracking-widest text-[var(--text-secondary)] uppercase font-light">Method</th>
                  <th className="pb-3 pr-4 text-[10px] font-mono tracking-widest text-[var(--text-secondary)] uppercase font-light">Path</th>
                  <th className="pb-3 text-[10px] font-mono tracking-widest text-[var(--text-secondary)] uppercase font-light">Description</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]/20">
                {[
                  ["POST", "/v1/observations", "Submit conversation for memory extraction"],
                  ["POST", "/v1/observations/batch", "Submit multiple observations at once"],
                  ["POST", "/v1/retrieve", "Hybrid semantic + lexical + graph retrieval"],
                  ["GET", "/v1/memories", "List memories for your organization"],
                  ["GET", "/v1/memories/{id}", "Get a single memory, including its fact triple and validity window"],
                  ["GET", "/v1/memories/{id}/explain", "Scoring breakdown and supersession lineage"],
                  ["GET", "/v1/entities/graph/{user_id}", "Get entity graph for a user"],
                  ["GET", "/v1/graph/traverse", "Multi-hop graph traversal"],
                  ["GET", "/v1/audit", "Tenant-scoped audit log"],
                  ["GET", "/v1/system/engine-status", "Local model server telemetry"],
                  ["GET", "/v1/keys", "List API keys for your organization"],
                  ["POST", "/v1/keys", "Create a new API key"],
                  ["DELETE", "/v1/keys/{id}", "Revoke an API key"],
                ].map(([method, path, desc]) => (
                  <tr key={`${method}:${path}`} className="hover:bg-[var(--muted)]/20 transition-colors duration-200">
                    <td className="py-3.5 pr-4">
                      <Badge className="font-mono text-[9px]">{method}</Badge>
                    </td>
                    <td className="py-3.5 pr-4 font-mono text-xs text-[var(--foreground)]">{path}</td>
                    <td className="py-3.5 text-xs text-[var(--text-secondary)] font-light">{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

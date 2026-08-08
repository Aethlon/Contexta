import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { requireSession } from "@/lib/auth-helpers";
import { listApiKeysAction } from "@/app/actions";
import { Tabs } from "@/components/ui/tabs";
import { CopyButton } from "./copy-button";

export default async function DocsPage() {
  const session = await requireSession();
  const keys = await listApiKeysAction();
  const latestKey = Array.isArray(keys) && keys.length > 0 ? keys[0] : null;

  const userId = session.user.id;
  const orgId = session.user.org_id;
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
    <div className="space-y-8 animate-fade-in">
      {/* Welcome Header */}
      <div className="border-b border-[var(--color-graphite)]/30 pb-6">
        <Badge>Setup</Badge>
        <h2 className="mt-3 text-2xl font-light tracking-tight text-[var(--color-ghost)]">Quick Start</h2>
        <p className="mt-1 text-sm font-light text-[var(--color-smoke)]">
          Integrate contexta into your agent. All IDs below are pre-filled from your account.
        </p>
      </div>

      {!latestKey ? (
        <div className="flex items-start gap-3 border border-red-500/20 bg-red-500/5 p-4 rounded-xl">
          <span className="text-sm font-light text-red-400">
            No API key found. <a href="/dashboard/api-keys" className="underline font-normal text-[var(--color-ghost)]">Create one first</a> to see your personalized setup.
          </span>
        </div>
      ) : null}

      {/* Account Info Cards */}
      <div className="grid gap-6 md:grid-cols-4">
        {[
          { label: "Org ID", value: orgId?.slice(0, 18) + "…" },
          { label: "User ID", value: userId?.slice(0, 18) + "…" },
          { label: "API Key", value: (latestKey?.prefix ?? "—") + "…" },
          { label: "API URL", value: apiUrl },
        ].map((item) => (
          <Card key={item.label}>
            <CardContent className="p-4 space-y-1">
              <p className="text-[10px] font-mono tracking-widest uppercase text-[var(--color-smoke)]">{item.label}</p>
              <code className="block truncate font-mono text-xs text-[var(--color-ghost)]">{item.value}</code>
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
                      <pre className="overflow-x-auto rounded-xl bg-[var(--color-abyss)] p-4 font-mono text-xs text-[var(--color-smoke)] border border-[var(--color-graphite)]/30 leading-relaxed">{envVars}</pre>
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
                      <pre className="overflow-x-auto rounded-xl bg-[var(--color-abyss)] p-4 font-mono text-xs text-[var(--color-smoke)] border border-[var(--color-graphite)]/30 leading-relaxed">{curlObserve}</pre>
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
                      <pre className="overflow-x-auto rounded-xl bg-[var(--color-abyss)] p-4 font-mono text-xs text-[var(--color-smoke)] border border-[var(--color-graphite)]/30 leading-relaxed">{curlRetrieve}</pre>
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
                    Install: <code className="rounded-md bg-[var(--color-abyss)] border border-[var(--color-graphite)]/30 px-2 py-1 font-mono text-xs text-[var(--color-ghost)] ml-1.5">pip install contexta-client</code>
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="relative">
                    <pre className="overflow-x-auto rounded-xl bg-[var(--color-abyss)] p-4 font-mono text-xs text-[var(--color-smoke)] border border-[var(--color-graphite)]/30 leading-relaxed">{pythonSdk}</pre>
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
                    Install: <code className="rounded-md bg-[var(--color-abyss)] border border-[var(--color-graphite)]/30 px-2 py-1 font-mono text-xs text-[var(--color-ghost)] ml-1.5">npm install contexta-client</code>
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="relative">
                    <pre className="overflow-x-auto rounded-xl bg-[var(--color-abyss)] p-4 font-mono text-xs text-[var(--color-smoke)] border border-[var(--color-graphite)]/30 leading-relaxed">{jsCode}</pre>
                    <CopyButton text={jsCode} />
                  </div>
                </CardContent>
              </Card>
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
                <tr className="border-b border-[var(--color-graphite)]/30 text-left">
                  <th className="pb-3 pr-4 text-[10px] font-mono tracking-widest text-[var(--color-smoke)] uppercase font-light">Method</th>
                  <th className="pb-3 pr-4 text-[10px] font-mono tracking-widest text-[var(--color-smoke)] uppercase font-light">Path</th>
                  <th className="pb-3 text-[10px] font-mono tracking-widest text-[var(--color-smoke)] uppercase font-light">Description</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-graphite)]/20">
                {[
                  ["POST", "/v1/observations", "Submit conversation for memory extraction"],
                  ["POST", "/v1/observations/batch", "Submit multiple observations at once"],
                  ["POST", "/v1/retrieve", "Hybrid semantic + keyword + graph retrieval"],
                  ["GET", "/v1/memories", "List memories for your organization"],
                  ["GET", "/v1/memories/{id}", "Get a single memory with full details"],
                  ["GET", "/v1/entities/graph/{user_id}", "Get entity graph for a user"],
                  ["GET", "/v1/keys", "List API keys for your organization"],
                  ["POST", "/v1/keys", "Create a new API key"],
                  ["DELETE", "/v1/keys/{id}", "Revoke an API key"],
                  ["GET", "/v1/usage", "Current period usage statistics"],
                ].map(([method, path, desc]) => (
                  <tr key={`${method}:${path}`} className="hover:bg-[var(--color-charcoal)]/20 transition-colors duration-200">
                    <td className="py-3.5 pr-4">
                      <Badge className="font-mono text-[9px]">{method}</Badge>
                    </td>
                    <td className="py-3.5 pr-4 font-mono text-xs text-[var(--color-ghost)]">{path}</td>
                    <td className="py-3.5 text-xs text-[var(--color-smoke)] font-light">{desc}</td>
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

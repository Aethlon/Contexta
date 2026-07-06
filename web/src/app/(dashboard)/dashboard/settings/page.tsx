import { requireSession } from "@/lib/auth-helpers";
import { listApiKeysAction, getUsageAction } from "@/app/actions";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Database, KeyRound, Server, Cpu } from "lucide-react";

export const revalidate = 30;

export default async function SettingsPage() {
  const session = await requireSession();
  const [keys, usage] = await Promise.all([
    listApiKeysAction(),
    getUsageAction(),
  ]);

  const apiUrl = process.env.CONTEXTA_API_URL ?? "http://localhost:8000";
  const llmProvider = process.env.CONTEXTA_LLM_PROVIDER ?? "deepseek";
  const llmModel = process.env.CONTEXTA_LLM_MODEL ?? "deepseek-chat";
  const embeddingProvider = process.env.CONTEXTA_EMBEDDING_PROVIDER ?? "deterministic";

  return (
    <div className="max-w-3xl space-y-8 animate-fade-in">
      {/* Header */}
      <div className="border-b border-[var(--color-graphite)]/30 pb-6">
        <Badge>Settings</Badge>
        <h2 className="mt-3 text-2xl font-light tracking-tight text-[var(--color-ghost)]">Organization</h2>
        <p className="mt-1 text-sm font-light text-[var(--color-smoke)]">
          Account details, API keys, and backend configuration.
        </p>
      </div>

      {/* Backend Status Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2.5 text-base">
            <Server className="h-4.5 w-4.5 text-[var(--color-smoke)]" strokeWidth={1.2} /> Backend Status
          </CardTitle>
          <CardDescription>Connection status and configured providers.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-4 space-y-1">
              <p className="text-[10px] font-mono tracking-widest uppercase text-[var(--color-smoke)]">API URL</p>
              <code className="block font-mono text-xs text-[var(--color-ghost)] truncate">{apiUrl}</code>
            </div>
            <div className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-4 space-y-1.5">
              <p className="text-[10px] font-mono tracking-widest uppercase text-[var(--color-smoke)]">LLM Provider</p>
              <div className="flex items-center gap-2 text-xs">
                <Badge>{llmProvider}</Badge>
                <span className="font-mono text-[var(--color-smoke)]">{llmModel}</span>
              </div>
            </div>
            <div className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-4 space-y-1">
              <p className="text-[10px] font-mono tracking-widest uppercase text-[var(--color-smoke)]">Embedding Provider</p>
              <div>
                <Badge>{embeddingProvider}</Badge>
              </div>
            </div>
            <div className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-4 space-y-1">
              <p className="text-[10px] font-mono tracking-widest uppercase text-[var(--color-smoke)]">Storage</p>
              <p className="text-xs text-[var(--color-ghost)] font-light">PostgreSQL + pgvector + Redis</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Usage Summary Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2.5 text-base">
            <Database className="h-4.5 w-4.5 text-[var(--color-smoke)]" strokeWidth={1.2} /> Usage Summary
          </CardTitle>
          <CardDescription>Current period metrics.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            {[
              { label: "Observations", value: usage?.observations ?? 0 },
              { label: "Retrievals", value: usage?.retrievals ?? 0 },
              { label: "Memory writes", value: usage?.memory_writes ?? 0 },
            ].map((item) => (
              <div key={item.label} className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-4 space-y-1">
                <p className="text-[10px] font-mono tracking-widest uppercase text-[var(--color-smoke)]">{item.label}</p>
                <p className="font-mono text-lg text-[var(--color-ghost)] tabular-nums">{item.value}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Account Info Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2.5 text-base">
            <Cpu className="h-4.5 w-4.5 text-[var(--color-smoke)]" strokeWidth={1.2} /> Your Account
          </CardTitle>
          <CardDescription>Profile details from your session.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-1">
              <p className="text-[10px] font-mono tracking-widest uppercase text-[var(--color-smoke)]">Email</p>
              <p className="text-sm font-light text-[var(--color-ghost)]">{session.user.email}</p>
            </div>
            <div className="space-y-1">
              <p className="text-[10px] font-mono tracking-widest uppercase text-[var(--color-smoke)]">Name</p>
              <p className="text-sm font-light text-[var(--color-ghost)]">{session.user.name}</p>
            </div>
            <div className="space-y-1">
              <p className="text-[10px] font-mono tracking-widest uppercase text-[var(--color-smoke)]">User ID</p>
              <code className="text-xs font-mono text-[var(--color-ghost)]">{session.user.id?.slice(0, 18)}…</code>
            </div>
            <div className="space-y-1">
              <p className="text-[10px] font-mono tracking-widest uppercase text-[var(--color-smoke)]">Org ID</p>
              <code className="text-xs font-mono text-[var(--color-ghost)]">{session.user.org_id?.slice(0, 18)}…</code>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* API Keys Table Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2.5 text-base">
            <KeyRound className="h-4.5 w-4.5 text-[var(--color-smoke)]" strokeWidth={1.2} /> Active API Keys
          </CardTitle>
          <CardDescription>Keys created for this organization.</CardDescription>
        </CardHeader>
        <CardContent>
          {(keys as any[])?.length === 0 ? (
            <p className="text-sm font-light text-[var(--color-smoke)] py-4 text-center">
              No API keys yet. <a href="/dashboard/api-keys" className="underline hover:text-[var(--color-ghost)] transition-colors">Create one</a>.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Prefix</TableHead>
                  <TableHead>Scopes</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Last used</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(keys as any[]).map((key: any) => (
                  <TableRow key={key.id} className="hover:bg-[var(--color-charcoal)]/30 transition-colors duration-200">
                    <TableCell className="font-normal text-[var(--color-ghost)]">{key.name}</TableCell>
                    <TableCell className="font-mono text-xs text-[var(--color-smoke)]">{key.prefix}…</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {key.scopes?.map((scope: string) => <Badge key={scope}>{scope}</Badge>)}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-[var(--color-smoke)]">
                      {new Date(key.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-xs text-[var(--color-smoke)]">
                      {key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : "Never"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Backend ENV Variables Configuration Card */}
      <Card>
        <CardHeader>
          <CardTitle>Configuration</CardTitle>
          <CardDescription>These are set via environment variables on the backend.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2.5">
          {[
            { key: "CONTEXTA_LLM_PROVIDER", desc: "LLM provider (openai, deepseek)" },
            { key: "CONTEXTA_LLM_MODEL", desc: "Model name (deepseek-chat, gpt-4o-mini, etc.)" },
            { key: "CONTEXTA_LLM_BASE_URL", desc: "API base URL for the LLM" },
            { key: "CONTEXTA_LLM_API_KEY", desc: "Your LLM provider API key" },
            { key: "CONTEXTA_EMBEDDING_PROVIDER", desc: "Embedding provider (openai, deterministic)" },
            { key: "CONTEXTA_EMBEDDING_API_KEY", desc: "Embedding API key (if using OpenAI)" },
            { key: "CONTEXTA_DATABASE_URL", desc: "PostgreSQL connection string" },
            { key: "CONTEXTA_REDIS_URL", desc: "Redis connection string" },
          ].map((env) => (
            <div key={env.key} className="flex items-center justify-between rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] px-4 py-3 text-xs">
              <code className="font-mono text-[var(--color-ghost)]">{env.key}</code>
              <span className="font-light text-[var(--color-smoke)]">{env.desc}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

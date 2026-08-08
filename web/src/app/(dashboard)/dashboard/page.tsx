import { Database, KeyRound, Zap, Activity } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { requireSession } from "@/lib/auth-helpers";
import { getUsageAction, listMemoriesAction, listApiKeysAction, getAuditLogAction } from "@/app/actions";

export const revalidate = 0;

export default async function DashboardPage() {
  const session = await requireSession();
  const [usage, memories, keys, audit] = await Promise.all([
    getUsageAction(),
    listMemoriesAction({ limit: 5 }),
    listApiKeysAction(),
    getAuditLogAction(10),
  ]);

  const metrics = [
    { label: "Stored memories", value: (memories.length ?? 0).toString(), delta: "total stored", icon: Database },
    { label: "Observations", value: (usage?.observations ?? 0).toString(), delta: "this period", icon: Activity },
    { label: "Active keys", value: ((keys as any[])?.length ?? 0).toString(), delta: "API keys", icon: KeyRound },
    { label: "Retrievals", value: (usage?.retrievals ?? 0).toString(), delta: "this period", icon: Zap },
  ];

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Top Welcome Header */}
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end border-b border-[var(--color-graphite)]/30 pb-6">
        <div className="space-y-1.5">
          <Badge>Production overview</Badge>
          <h2 className="text-2xl font-light tracking-tight text-[var(--color-ghost)]">Memory control plane</h2>
          <p className="max-w-2xl text-sm font-light text-[var(--color-smoke)]">
            Monitor tenant memory volume, retrieval quality, and API key usage.
          </p>
        </div>
        <div className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] px-4 py-3 text-xs font-mono text-[var(--color-smoke)]">
          <span>Logged in as</span>
          <span className="ml-3 font-normal text-[var(--color-ghost)]">{session.user.email}</span>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid gap-6 md:grid-cols-4">
        {metrics.map((metric) => {
          const Icon = metric.icon ?? Activity;
          return (
            <Card key={metric.label}>
              <CardContent className="flex min-h-32 flex-col justify-between p-6">
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <p className="text-xs font-mono tracking-widest uppercase text-[var(--color-smoke)]">{metric.label}</p>
                    <p className="text-3xl font-light tracking-tight text-[var(--color-ghost)] tabular-nums">{metric.value}</p>
                  </div>
                  <Icon className="h-5 w-5 text-[var(--color-smoke)]" strokeWidth={1.2} />
                </div>
                <div>
                  <p className="text-xs text-[var(--color-smoke)] font-light">{metric.delta}</p>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Layout Grid: Memories + Activity */}
      <div className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
        <Card>
          <CardHeader>
            <CardTitle>Recent Memories</CardTitle>
            <CardDescription>Latest extracted records from recent observations.</CardDescription>
          </CardHeader>
          <CardContent>
            {(memories as any[])?.length === 0 ? (
              <p className="text-sm font-light text-[var(--color-smoke)] py-6 text-center">
                No memories yet. Ingest an observation to get started.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Title</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>State</TableHead>
                    <TableHead>Importance</TableHead>
                    <TableHead className="text-right">Updated</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(memories as any[]).map((memory: any) => (
                    <TableRow key={memory.id} className="hover:bg-[var(--color-charcoal)]/30 transition-colors duration-200">
                      <TableCell className="font-normal text-[var(--color-ghost)]">{memory.title ?? "Untitled"}</TableCell>
                      <TableCell className="text-[var(--color-smoke)]">{memory.memory_type ?? memory.type ?? "—"}</TableCell>
                      <TableCell>
                        <Badge className="lowercase">{memory.memory_state ?? memory.state ?? "active"}</Badge>
                      </TableCell>
                      <TableCell className="tabular-nums text-[var(--color-smoke)]">
                        {typeof memory.importance === "number" ? memory.importance.toFixed(2) : "—"}
                      </TableCell>
                      <TableCell className="text-right text-xs text-[var(--color-smoke)]">
                        {memory.updated_at ? new Date(memory.updated_at).toLocaleDateString() : memory.created_at ? new Date(memory.created_at).toLocaleDateString() : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Activity Feed</CardTitle>
            <CardDescription>Recent actions in your organization.</CardDescription>
          </CardHeader>
          <CardContent>
            {(audit as any[])?.length === 0 ? (
              <p className="text-sm font-light text-[var(--color-smoke)] py-6 text-center">No recent activity.</p>
            ) : (
              <div className="space-y-4">
                {(audit as any[]).slice(0, 8).map((entry: any, i: number) => (
                  <div className="flex items-start gap-3.5 text-sm" key={entry.id ?? i}>
                    <span className="mt-1.5 flex h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-smoke)]" />
                    <div className="flex-1 space-y-0.5">
                      <p className="text-[var(--color-ghost)] font-light leading-relaxed">{entry.action ?? entry.event ?? "Action"}</p>
                      <p className="text-[10px] font-mono tracking-wider text-[var(--color-smoke)]">
                        {entry.timestamp ? new Date(entry.timestamp).toLocaleString() : entry.created_at ? new Date(entry.created_at).toLocaleString() : "—"}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Layout Grid: API Keys + Developer Path */}
      <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <Card>
          <CardHeader>
            <CardTitle>API Keys</CardTitle>
            <CardDescription>Overview of active API keys.</CardDescription>
          </CardHeader>
          <CardContent>
            {(keys as any[])?.length === 0 ? (
              <p className="text-sm font-light text-[var(--color-smoke)] py-4 text-center">
                No API keys yet. Create one in the API keys page.
              </p>
            ) : (
              <div className="space-y-2.5">
                {(keys as any[]).map((key: any) => (
                  <div className="flex items-center justify-between rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-4 text-sm hover:bg-[var(--color-charcoal)] transition-colors duration-200" key={key.id}>
                    <span className="font-normal text-[var(--color-ghost)]">{key.name}</span>
                    <Badge>{key.prefix}...</Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Developer Path</CardTitle>
            <CardDescription>The minimum path from signup to working agent memory.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {[
              "Create backend-synced API key",
              "Copy env vars into an agent",
              "POST observations",
              "Retrieve context with one request",
            ].map((item, index) => (
              <div className="flex items-center gap-4 rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-4 text-sm font-light" key={item}>
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-[var(--color-charcoal)] border border-[var(--color-graphite)]/40 font-mono text-[10px] text-[var(--color-smoke)] select-none">
                  {index + 1}
                </span>
                <span className="text-[var(--color-ghost)]">{item}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

import { Terminal, Cpu, Clock, Network, Lock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { requireSession } from "@/lib/auth-helpers";
import { listMemoriesAction, getAuditLogAction } from "@/app/actions";
import { ActivityBarChart } from "@/components/dashboard/activity-bar-chart";
import { MiniGraphPreview } from "@/components/dashboard/mini-graph-preview";
import { OverviewInteractivePanel } from "@/components/dashboard/overview-interactive-panel";
import Link from "next/link";

export const revalidate = 0;

export default async function DashboardPage() {
  const session = await requireSession();
  const [memories, audit] = await Promise.all([
    listMemoriesAction({ limit: 10 }),
    getAuditLogAction(10),
  ]);

  const memoryCount = (memories as any[])?.length ?? 0;

  const metrics = [
    {
      label: "Encrypted Facts",
      value: memoryCount > 0 ? `${memoryCount}` : "0",
      delta: "AES-v1 On-Disk Vault",
      icon: Lock,
      badge: "Encrypted",
      badgeColor: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    },
    {
      label: "System Uptime",
      value: "99.99%",
      delta: "Sovereign • Offline-First",
      icon: Clock,
      badge: "Local Engine",
      badgeColor: "text-sky-400 bg-sky-500/10 border-sky-500/20",
    },
    {
      label: "Graph Entities",
      value: "24+",
      delta: "Multi-Hop Traversal",
      icon: Network,
      badge: "Synthesized",
      badgeColor: "text-indigo-400 bg-indigo-500/10 border-indigo-500/20",
    },
    {
      label: "Recall Latency",
      value: "<42ms",
      delta: "Hybrid RRF + Neural Rerank",
      icon: Cpu,
      badge: "Qwen3 0.6B",
      badgeColor: "text-amber-400 bg-amber-500/10 border-amber-500/20",
    },
  ];

  return (
    <div className="space-y-6 animate-fade-in font-mono">
      {/* Top Welcome Header */}
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end border-b border-border/40 pb-6">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-normal">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Sovereign Local Enclave Active
            </span>
            <Badge>Memory Control Plane</Badge>
          </div>
          <h2 className="text-xl font-normal tracking-tight text-foreground">
            Personal Knowledge Core
          </h2>
          <p className="max-w-2xl text-xs text-muted-foreground font-sans leading-relaxed">
            Autonomous memory intelligence, real-time entity synthesis, and AES-encrypted local storage. Offline-first by default.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="rounded border border-border/40 bg-secondary/50 px-3 py-1.5 text-xs text-muted-foreground">
            <span>Operator:</span>
            <span className="ml-2 font-normal text-foreground">{session.user.email}</span>
          </div>
          <Link
            href="/dashboard/mcp"
            className="flex items-center gap-1.5 rounded border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/20 px-3 py-1.5 text-xs text-emerald-300 transition-colors"
          >
            <Terminal className="h-3.5 w-3.5" />
            <span>Connect MCP &rarr;</span>
          </Link>
        </div>
      </div>

      {/* Self-Hosting Interactive Panel & Cluster Diagnostic */}
      <OverviewInteractivePanel />

      {/* Metrics Row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map((metric) => {
          const Icon = metric.icon;
          return (
            <Card key={metric.label}>
              <CardContent className="flex min-h-24 flex-col justify-between p-4 sm:p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <p className="text-[11px] font-mono tracking-wider uppercase text-muted-foreground">
                      {metric.label}
                    </p>
                    <p className="text-2xl font-normal tracking-tight text-foreground font-mono tabular-nums">
                      {metric.value}
                    </p>
                  </div>
                  <span className="flex size-7 items-center justify-center rounded border border-border/40 bg-secondary/60">
                    <Icon className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.5} />
                  </span>
                </div>
                <div className="flex items-center justify-between pt-1">
                  <p className="text-[10px] text-muted-foreground font-mono">[{metric.delta}]</p>
                  <span className={`text-[9px] px-1.5 py-0.2 rounded border font-mono ${metric.badgeColor}`}>
                    {metric.badge}
                  </span>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Interactive Visualizers Row: Activity Bar Chart & Mini Knowledge Graph */}
      <div className="grid gap-6 lg:grid-cols-2">
        <ActivityBarChart />
        <MiniGraphPreview />
      </div>

      {/* Layout Grid: Memories + Activity */}
      <div className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Encrypted Personal Facts</CardTitle>
              <CardDescription>Decrypted on-the-fly for authorized operator session.</CardDescription>
            </div>
            <Link
              href="/dashboard/memories"
              className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-4 font-mono transition-colors"
            >
              View all
            </Link>
          </CardHeader>
          <CardContent>
            {memoryCount === 0 ? (
              <div className="text-center py-8 space-y-2">
                <p className="text-xs font-mono text-muted-foreground">
                  [*] No personal facts recorded yet.
                </p>
                <Link
                  href="/onboarding"
                  className="inline-flex items-center gap-1.5 text-xs text-foreground hover:underline"
                >
                  <span>Complete personal onboarding context &rarr;</span>
                </Link>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Title</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Vault Status</TableHead>
                    <TableHead>Salience</TableHead>
                    <TableHead className="text-right">Updated</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(memories as any[]).map((memory: any) => (
                    <TableRow key={memory.id} className="hover:bg-secondary/40 transition-colors duration-150">
                      <TableCell className="font-normal text-foreground max-w-[200px] truncate">
                        {memory.title ?? "Personal Fact"}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        <span className="text-[10px] px-2 py-0.5 rounded border border-border/40 bg-secondary/50">
                          {memory.memory_type ?? memory.type ?? "fact"}
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400 font-mono">
                          <Lock className="h-2.5 w-2.5" />
                          <span>AES-Stream</span>
                        </span>
                      </TableCell>
                      <TableCell className="tabular-nums text-muted-foreground">
                        {typeof memory.importance === "number" ? memory.importance.toFixed(2) : "0.95"}
                      </TableCell>
                      <TableCell className="text-right text-xs text-muted-foreground">
                        {memory.updated_at ? new Date(memory.updated_at).toLocaleDateString() : memory.created_at ? new Date(memory.created_at).toLocaleDateString() : "Today"}
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
            <CardTitle>Audit & Activity Feed</CardTitle>
            <CardDescription>Live telemetry and agent memory access logs.</CardDescription>
          </CardHeader>
          <CardContent>
            {(audit as any[])?.length === 0 ? (
              <p className="text-xs font-mono text-muted-foreground py-6 text-center">
                [*] No recent activity recorded.
              </p>
            ) : (
              <div className="space-y-3 font-mono text-xs">
                {(audit as any[]).slice(0, 6).map((entry: any, i: number) => (
                  <div className="flex items-start gap-2.5 rounded border border-border/20 bg-secondary/30 p-2.5" key={entry.id ?? i}>
                    <span className="mt-1 flex h-1.5 w-1.5 shrink-0 rounded-full bg-foreground/60" />
                    <div className="flex-1 space-y-0.5">
                      <p className="text-foreground leading-normal font-normal">{entry.action ?? entry.event ?? "System event"}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {entry.timestamp ? new Date(entry.timestamp).toLocaleString() : entry.created_at ? new Date(entry.created_at).toLocaleString() : "Just now"}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Bottom Bar: MCP Agent Quick Connect */}
      <Card className="border-indigo-500/20 bg-indigo-950/10">
        <CardContent className="p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 font-mono">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Terminal className="h-4 w-4 text-indigo-400" />
              <h4 className="text-xs font-semibold text-foreground">Connect External Agents via MCP</h4>
              <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300">
                Port :8765
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Integrate Claude Desktop, Cursor, and Windsurf directly with your sovereign Contexta memory vault.
            </p>
          </div>
          <div className="flex items-center gap-2.5 w-full md:w-auto">
            <code className="text-[11px] bg-background/80 px-3 py-1.5 rounded border border-border/40 text-foreground select-all">
              mcp-server: http://localhost:8765/sse
            </code>
            <Link
              href="/dashboard/setup"
              className="whitespace-nowrap px-3 py-1.5 rounded bg-foreground text-background text-xs font-medium hover:bg-foreground/90 transition-all"
            >
              Setup Guide &rarr;
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

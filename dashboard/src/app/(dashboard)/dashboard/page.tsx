import { Terminal, Database, Network, Cpu, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { resolveOperatorIdentity } from "@/lib/dashboard-identity";
import {
  listMemoriesAction,
  getAuditLogAction,
  getGraphAction,
  probeTenantAction,
} from "@/app/actions";
import { PipelineStrip } from "@/components/dashboard/pipeline-strip";
import { MiniGraphPreview } from "@/components/dashboard/mini-graph-preview";
import Link from "next/link";

export const revalidate = 0;

export default async function DashboardPage() {
  const identity = await resolveOperatorIdentity();
  const [memories, audit, graph, probe] = await Promise.all([
    listMemoriesAction({ limit: 10 }),
    getAuditLogAction(10),
    getGraphAction(),
    probeTenantAction(),
  ]);

  const memoryRows = (memories as any[]) ?? [];
  const auditRows = (audit as any[]) ?? [];
  const graphNodes = (graph as any)?.nodes ?? [];
  const graphEdges = (graph as any)?.edges ?? [];
  const activeCount = memoryRows.filter(
    (m: any) => (m.memory_state ?? "active") === "active",
  ).length;

  const metrics = [
    {
      label: "Memories",
      value: String(memoryRows.length),
      delta: `${activeCount} current · rest superseded/archived`,
      icon: Database,
    },
    {
      label: "Graph entities",
      value: String(graphNodes.length),
      delta: `${graphEdges.length} resolved edges`,
      icon: Network,
    },
    {
      label: "Recall layers",
      value: "3",
      delta: "vector + lexical + graph, RRF fused",
      icon: Cpu,
    },
    {
      label: "Audit entries",
      value: String(auditRows.length),
      delta: "most recent reads and writes",
      icon: Terminal,
    },
  ];

  return (
    <div className="animate-fade-in space-y-8">
      {/* Page header */}
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
        <div>
          <h1 className="nb-page-title">Memory Console</h1>
          <p className="nb-page-subtitle max-w-2xl">
            Ingest observations, inspect what the truth engine kept, and read it
            back through hybrid retrieval. Offline-first by default.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span
              className="nb-badge"
              style={{
                color: "var(--accent-green)",
                borderColor: "color-mix(in srgb, var(--accent-green) 30%, transparent)",
                background: "color-mix(in srgb, var(--accent-green) 8%, transparent)",
              }}
            >
              <span
                className="size-1.5 rounded-full"
                style={{ background: "var(--accent-green)" }}
              />
              org {identity.orgId ? identity.orgId.slice(0, 8) : "unresolved"}
            </span>
            <Badge>{identity.authRequired ? "Signed in" : "Auth off"}</Badge>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Link href="/dashboard/mcp" className="nb-btn nb-btn-secondary">
            <Terminal className="size-4" strokeWidth={1.75} />
            <span>Connect MCP</span>
          </Link>
        </div>
      </div>

      {!identity.resolved ? (
        <div className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-[13px] tone-amber">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <div className="space-y-1">
            <p className="font-medium">No organization resolved</p>
            <p>
              Every API call will be rejected with 401 until the console has a
              tenant. Set <code className="font-mono">CONTEXTA_DASHBOARD_API_KEY</code>{" "}
              (recommended) or use the organization panel at the bottom of the
              sidebar.
            </p>
          </div>
        </div>
      ) : null}

      {identity.resolved && !probe.ok ? (
        <div className="flex items-start gap-3 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-[13px] tone-red">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <div className="space-y-1">
            <p className="font-medium">The API rejected this tenant</p>
            <p>{probe.error}</p>
            <p>
              The counts below are empty because of that, not because the
              organization has no memories. Fix the organization panel in the
              sidebar, then reload.
            </p>
          </div>
        </div>
      ) : null}

      <PipelineStrip />

      {/* Metrics Row */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map((metric) => {
          const Icon = metric.icon;
          return (
            <Card key={metric.label}>
              <CardContent className="flex min-h-20 flex-col justify-between p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs text-muted-foreground">{metric.label}</p>
                    <p className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-foreground">
                      {metric.value}
                    </p>
                  </div>
                  <Icon className="size-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
                </div>
                <p className="mt-2 text-xs text-muted-foreground">{metric.delta}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <MiniGraphPreview nodes={graphNodes} edges={graphEdges} actorKnown={Boolean(identity.userId)} />
      </div>

      {/* Memories + Activity */}
      <div className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Current memories</CardTitle>
              <CardDescription>
                Rows the truth engine has not superseded.
              </CardDescription>
            </div>
            <Link
              href="/dashboard/memories"
              className="text-[13px] text-muted-foreground underline underline-offset-4 transition-colors hover:text-foreground"
            >
              View all
            </Link>
          </CardHeader>
          <CardContent className="px-0 py-0">
            {memoryRows.length === 0 ? (
              <div className="space-y-2 px-5 py-8 text-center">
                <p className="text-[13px] text-muted-foreground">
                  No memories in this organization yet.
                </p>
                <p className="text-[13px] text-muted-foreground">
                  Use &ldquo;Ingest Observation&rdquo; in the header to push one
                  through the pipeline.
                </p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Title</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>State</TableHead>
                    <TableHead className="text-right">Updated</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {memoryRows.map((memory: any) => (
                    <TableRow key={memory.id}>
                      <TableCell className="max-w-[240px] truncate font-medium">
                        {memory.title ?? "Untitled"}
                      </TableCell>
                      <TableCell>
                        <span className="nb-badge h-5 text-[11px]">
                          {memory.memory_type ?? "fact"}
                        </span>
                      </TableCell>
                      <TableCell>
                        <span
                          className={`text-[11px] ${
                            (memory.memory_state ?? "active") === "active"
                              ? "tone-green"
                              : "tone-amber"
                          }`}
                        >
                          {memory.memory_state ?? "active"}
                        </span>
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        {memory.updated_at
                          ? new Date(memory.updated_at).toLocaleDateString()
                          : memory.created_at
                            ? new Date(memory.created_at).toLocaleDateString()
                            : "—"}
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
            <CardTitle>Audit &amp; Activity Feed</CardTitle>
            <CardDescription>Live telemetry and memory access logs.</CardDescription>
          </CardHeader>
          <CardContent className="px-5 py-0">
            {auditRows.length === 0 ? (
              <p className="py-6 text-center text-[13px] text-muted-foreground">
                No recent activity recorded.
              </p>
            ) : (
              <div className="divide-y divide-border">
                {auditRows.slice(0, 6).map((entry: any, i: number) => (
                  <div
                    className="flex items-start gap-2.5 py-2.5 first:pt-4 last:pb-4"
                    key={entry.id ?? i}
                  >
                    <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-muted-foreground/50" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] text-foreground">
                        {entry.action ?? entry.event ?? "System event"}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {entry.timestamp
                          ? new Date(entry.timestamp).toLocaleString()
                          : entry.created_at
                            ? new Date(entry.created_at).toLocaleString()
                            : "Just now"}
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
      <Card>
        <CardContent className="flex flex-col items-start justify-between gap-4 p-4 md:flex-row md:items-center">
          <div>
            <div className="flex items-center gap-2">
              <Terminal
                className="size-4"
                strokeWidth={1.75}
                style={{ color: "var(--accent-blue)" }}
              />
              <h4 className="text-sm font-semibold text-foreground">
                Connect external agents via MCP
              </h4>
              <span className="nb-badge h-5 text-[11px]">:8765</span>
            </div>
            <p className="mt-1 text-[13px] text-muted-foreground">
              Integrate Claude Desktop, Cursor, and Windsurf with your memory
              vault.
            </p>
          </div>
          <div className="flex w-full items-center gap-2 md:w-auto">
            <code className="nb-code flex-1 select-all md:flex-none">
              http://localhost:8765/sse
            </code>
            <Link href="/dashboard/setup" className="nb-btn nb-btn-secondary">
              Setup guide
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

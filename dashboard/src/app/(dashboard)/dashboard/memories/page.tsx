import Link from "next/link";
import { Database, FileText, Rocket, Search, ShieldCheck, TriangleAlert, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { resolveOperatorIdentity } from "@/lib/dashboard-identity";
import {
  listMemoriesAction,
  getMemoriesAction,
  getGraphAction,
  probeTenantAction,
} from "@/app/actions";
import { MemoryRow } from "./memory-row";
import { EntityGraphView } from "./entity-graph-view";
import { MemorySearch } from "./memory-search";
import { FirstRunLink, RevealTenantButton } from "@/components/reveal-tenant-button";

export const revalidate = 0;

export default async function MemoriesPage({
  searchParams,
}: {
  searchParams?: Promise<{ q?: string; type?: string; state?: string }>;
}) {
  const identity = await resolveOperatorIdentity();
  const params = searchParams ? await searchParams : {};
  const query = params.q?.trim();

  let memories: any[] = [];
  let graph: { nodes: any[]; edges: any[] } = { nodes: [], edges: [] };
  let error: string | null = null;
  const probe = await probeTenantAction();

  try {
    const [memoriesRes, graphRes] = await Promise.all([
      query
        ? getMemoriesAction(query, 100)
        : listMemoriesAction({
            limit: 100,
            memory_type: params.type,
            state: params.state,
          }),
      getGraphAction(),
    ]);
    memories = memoriesRes || [];
    graph = graphRes || { nodes: [], edges: [] };
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load data";
  }

  const activeCount = memories.filter(
    (m: any) => (m.memory_state ?? "active") === "active",
  ).length;
  const types = [...new Set(memories.map((m: any) => m.memory_type).filter(Boolean))];

  const memoryStats = [
    { label: "Records", value: memories.length, icon: Database },
    { label: "Current", value: activeCount, icon: ShieldCheck },
    { label: "Types", value: types.length, icon: FileText },
    {
      label: "Avg importance",
      value: memories.length
        ? (
            memories.reduce((s: number, m: any) => s + (m.importance ?? 0), 0) /
            memories.length
          ).toFixed(2)
        : "—",
      icon: Search,
    },
  ];

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Top Inspector Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between border-b border-[var(--border)]/30 pb-6">
        <div className="space-y-1.5">
          <Badge>Stored memory</Badge>
          <h2 className="text-2xl font-light tracking-tight text-[var(--foreground)]">
            Memory Inspector
          </h2>
          <p className="max-w-2xl text-sm font-light text-[var(--text-secondary)]">
            {identity.orgId ? (
              <>
                Browse every memory in organization{" "}
                <code className="font-mono">{identity.orgId.slice(0, 8)}</code>.
                Expand a row to see its fact triple and supersession lineage.
              </>
            ) : (
              "No organization is resolved yet, so there is nothing to browse. Set an API key in the sidebar, then reload."
            )}
          </p>
        </div>
        <div className="flex shrink-0">
          <MemorySearch />
        </div>
      </div>

      {error ? (
        <div className="flex items-start gap-3 border-b border-[var(--border)]/30 pb-4">
          <span className="text-sm font-light tone-red">{error}</span>
        </div>
      ) : null}

      {!probe.ok ? (
        <div className="flex items-start gap-3 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-[13px] tone-red">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <div className="space-y-2">
            <p className="font-medium">The API rejected this tenant</p>
            <p>{probe.error}</p>
            <p>
              The console cannot read anything until this is set. It is the
              quickest fix in the product: mint a key, paste it once, and the
              sidebar resolves the organization from it.
            </p>
            <div className="flex flex-wrap items-center gap-2 pt-0.5">
              <RevealTenantButton label="Open the organization panel" />
              <FirstRunLink label="Full first-run steps" />
            </div>
          </div>
        </div>
      ) : null}

      {/* Memory Stats Row. Hidden while the tenant is unresolved: a row of zeros
          reads as "this organization is empty" when it actually means "the API
          refused us", which is the opposite of what the operator needs to read. */}
      {probe.ok ? (
        <div className="grid gap-6 md:grid-cols-4">
          {memoryStats.map((stat) => {
            const Icon = stat.icon;
            return (
              <Card key={stat.label}>
                <CardContent className="flex items-start justify-between p-6">
                  <div className="space-y-1">
                    <p className="text-xs font-mono tracking-widest uppercase text-[var(--text-secondary)]">
                      {stat.label}
                    </p>
                    <p className="text-3xl font-light tracking-tight text-[var(--foreground)] tabular-nums">
                      {stat.value}
                    </p>
                  </div>
                  <Icon className="h-5 w-5 text-[var(--text-secondary)]" strokeWidth={1.2} />
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : null}

      {/* Main Content Layout Grid */}
      <div className="grid gap-6 lg:grid-cols-[1.3fr_0.7fr]">
        <Card>
          <CardHeader>
            <CardTitle>Memory Records</CardTitle>
            <CardDescription>
              {!probe.ok
                ? "Waiting on a tenant."
                : memories.length === 0
                  ? "Nothing stored yet."
                  : `${memories.length} records across ${types.length} types`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {query ? (
              <div className="mb-4 flex items-center justify-between rounded-lg border border-[var(--border)]/40 bg-[var(--card)] px-3 py-2 text-xs font-mono">
                <span className="text-[var(--text-secondary)]">
                  Search results for:{" "}
                  <strong className="text-[var(--foreground)]">{query}</strong>
                </span>
                <Link
                  href="/dashboard/memories"
                  className="inline-flex items-center gap-1 text-[var(--text-secondary)] transition-colors hover:text-[var(--foreground)]"
                >
                  <X className="size-3" /> Clear filter
                </Link>
              </div>
            ) : null}
            {memories.length === 0 ? (
              <div className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--card)] px-4 py-8 text-center text-sm font-light text-[var(--text-secondary)]">
                {probe.ok ? (
                  <>
                    <p>No memories yet.</p>
                    <p className="mt-1.5 text-xs">
                      Send an observation and the extractor will write them here.
                    </p>
                    <Link
                      href="/dashboard/welcome"
                      className="mt-4 inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs text-foreground transition-colors hover:bg-accent"
                    >
                      <Rocket className="size-3" strokeWidth={1.75} />
                      <span>Walk through the first run</span>
                    </Link>
                  </>
                ) : (
                  <p>
                    The API refused this tenant, so no records were loaded. Fix the
                    organization in the sidebar, then reload.
                  </p>
                )}
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[50px]" />
                    <TableHead>Title</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>State</TableHead>
                    <TableHead className="text-right">Importance</TableHead>
                    <TableHead className="text-right">Confidence</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {memories.map((memory: any) => (
                    <MemoryRow key={memory.id} memory={memory} />
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Entity Graph</CardTitle>
            <CardDescription>
              {!identity.userId
                ? "No actor UUID resolved, so the graph was not queried."
                : graph.nodes.length === 0
                  ? "No entities extracted yet."
                  : `${graph.nodes.length} entities`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {identity.userId ? (
              <EntityGraphView nodes={graph.nodes} edges={graph.edges} />
            ) : (
              <div className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--card)] px-4 py-6 text-center text-xs leading-relaxed text-[var(--text-secondary)]">
                <p>
                  The graph is queried by actor. The API resolves the actor from
                  the bootstrap key but does not expose it, so set{" "}
                  <code className="font-mono">CONTEXTA_DASHBOARD_USER_ID</code> or
                  enter a user id in the sidebar organization panel.
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

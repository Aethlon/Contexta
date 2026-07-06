import { Database, FileText, Search, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { requireSession } from "@/lib/auth-helpers";
import { listMemoriesAction, getGraphAction } from "@/app/actions";
import { MemoryRow } from "./memory-row";
import { EntityGraphView } from "./entity-graph-view";
import { MemorySearch } from "./memory-search";

export const revalidate = 0;

export default async function MemoriesPage() {
  await requireSession();
  let memories: any[] = [];
  let graph: { nodes: any[]; edges: any[] } = { nodes: [], edges: [] };
  let error: string | null = null;

  try {
    [memories, graph] = await Promise.all([
      listMemoriesAction({ limit: 100 }),
      getGraphAction(),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load data";
  }

  const activeCount = memories.filter((m: any) => (m.memory_state ?? "active") === "active").length;
  const types = [...new Set(memories.map((m: any) => m.memory_type).filter(Boolean))];

  const memoryStats = [
    { label: "Records", value: memories.length, icon: Database },
    { label: "Active", value: activeCount, icon: ShieldCheck },
    { label: "Types", value: types.length, icon: FileText },
    { label: "Avg Importance", value: memories.length ? (memories.reduce((s: number, m: any) => s + (m.importance ?? 0), 0) / memories.length).toFixed(2) : "—", icon: Search },
  ];

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Top Inspector Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between border-b border-[var(--color-graphite)]/30 pb-6">
        <div className="space-y-1.5">
          <Badge>Stored memory</Badge>
          <h2 className="text-2xl font-light tracking-tight text-[var(--color-ghost)]">Memory Inspector</h2>
          <p className="max-w-2xl text-sm font-light text-[var(--color-smoke)]">
            Browse, search, and explore every memory extracted from your observations.
          </p>
        </div>
        <div className="flex shrink-0">
          <MemorySearch />
        </div>
      </div>

      {error ? (
        <div className="flex items-start gap-3 border-b border-[var(--color-graphite)]/30 pb-4">
          <span className="text-sm font-light text-red-400">{error}</span>
        </div>
      ) : null}

      {/* Memory Stats Row */}
      <div className="grid gap-6 md:grid-cols-4">
        {memoryStats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label}>
              <CardContent className="flex items-start justify-between p-6">
                <div className="space-y-1">
                  <p className="text-xs font-mono tracking-widest uppercase text-[var(--color-smoke)]">{stat.label}</p>
                  <p className="text-3xl font-light tracking-tight text-[var(--color-ghost)] tabular-nums">{stat.value}</p>
                </div>
                <Icon className="h-5 w-5 text-[var(--color-smoke)]" strokeWidth={1.2} />
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Main Content Layout Grid */}
      <div className="grid gap-6 lg:grid-cols-[1.3fr_0.7fr]">
        <Card>
          <CardHeader>
            <CardTitle>Memory Records</CardTitle>
            <CardDescription>
              {memories.length === 0
                ? "No memories yet. Ingest an observation to create one."
                : `${memories.length} records across ${types.length} types`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {memories.length === 0 ? (
              <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-[var(--color-graphite)] bg-[var(--color-ash)] text-sm text-[var(--color-smoke)] font-light">
                Submit an observation to extract memories
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
              {graph.nodes.length === 0
                ? "No entities extracted yet."
                : `${graph.nodes.length} entities`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <EntityGraphView nodes={graph.nodes} edges={graph.edges} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

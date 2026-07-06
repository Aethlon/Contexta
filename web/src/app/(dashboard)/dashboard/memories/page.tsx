import { Database, FileText, Search, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs } from "@/components/ui/tabs";
import { requireSession } from "@/lib/auth-helpers";
import { getMemoriesAction } from "@/app/actions";
import { EntityGraph } from "@/components/entity-graph";
import { MemorySearch } from "./memory-search";

export const revalidate = 0;

export default async function MemoriesPage() {
  const session = await requireSession();
  let memories: any[] = [];
  let error: string | null = null;

  try {
    memories = await getMemoriesAction("", 100);
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load data";
  }

  const activeCount = memories.filter((m: any) => (m.memory_state ?? m.state) === "active").length;
  const inactiveCount = memories.length - activeCount;

  const memoryStats = [
    { label: "Records", value: memories.length, icon: Database },
    { label: "Active", value: activeCount, icon: ShieldCheck },
    { label: "Warm/cold", value: inactiveCount, icon: FileText },
    { label: "Indexed fields", value: "12", icon: Search },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <Badge>Stored memory</Badge>
          <h2 className="mt-3 text-2xl font-semibold">Memory Inspector</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
            See the exact details contexta stores for each extracted memory.
          </p>
        </div>
        <div className="flex gap-2">
          <MemorySearch />
          <Button variant="outline">Export</Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          Could not reach backend: {error}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-4">
        {memoryStats.map((stat) => {
          const Icon = stat.icon;
          return (
          <Card key={stat.label}>
            <CardContent className="flex items-start justify-between p-5">
              <div>
                <p className="text-sm text-muted-foreground">{stat.label}</p>
                <p className="mt-2 text-2xl font-semibold">{stat.value}</p>
              </div>
              <Icon className="h-5 w-5 text-muted-foreground" />
            </CardContent>
          </Card>
          );
        })}
      </div>

      <Tabs tabs={[
        {
          label: "Table",
          content: (
            <div className="space-y-6"><Card>
            <CardHeader>
              <CardTitle>Memory Records</CardTitle>
              <CardDescription>Compact index of extracted memory stored for this organization.</CardDescription>
            </CardHeader>
            <CardContent>
              {memories.length === 0 ? (
                <p className="text-sm text-muted-foreground">No memories yet. Ingest an observation to create one.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ID</TableHead>
                      <TableHead>Title</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>State</TableHead>
                      <TableHead>Importance</TableHead>
                      <TableHead>Confidence</TableHead>
                      <TableHead>Updated</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {memories.map((memory: any) => (
                      <TableRow key={memory.id}>
                        <TableCell className="font-mono text-xs text-muted-foreground">{memory.id?.slice(0, 8) ?? "—"}…</TableCell>
                        <TableCell className="font-medium">{memory.title ?? "Untitled"}</TableCell>
                        <TableCell>{memory.memory_type ?? memory.type ?? "—"}</TableCell>
                        <TableCell><Badge>{memory.memory_state ?? memory.state ?? "active"}</Badge></TableCell>
                        <TableCell>{typeof memory.importance === "number" ? memory.importance.toFixed(2) : "—"}</TableCell>
                        <TableCell>{typeof memory.confidence === "number" ? memory.confidence.toFixed(2) : "—"}</TableCell>
                        <TableCell className="text-muted-foreground">{memory.updated_at ? new Date(memory.updated_at).toLocaleDateString() : "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {memories.map((memory: any) => (
            <Card key={memory.id}>
              <CardHeader>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <CardTitle>{memory.title ?? "Untitled"}</CardTitle>
                    <CardDescription className="mt-1">
                      {memory.id} · {memory.memory_type ?? memory.type ?? "—"}
                    </CardDescription>
                  </div>
                  <Badge>{memory.memory_state ?? memory.state ?? "active"}</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="grid gap-3 md:grid-cols-3">
                  <div className="rounded-md border border-border bg-background p-3">
                    <p className="text-xs text-muted-foreground">Importance</p>
                    <p className="mt-1 font-mono text-lg">{typeof memory.importance === "number" ? memory.importance.toFixed(2) : "—"}</p>
                  </div>
                  <div className="rounded-md border border-border bg-background p-3">
                    <p className="text-xs text-muted-foreground">Confidence</p>
                    <p className="mt-1 font-mono text-lg">{typeof memory.confidence === "number" ? memory.confidence.toFixed(2) : "—"}</p>
                  </div>
                  <div className="rounded-md border border-border bg-background p-3">
                    <p className="text-xs text-muted-foreground">Tags</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {memory.tags?.length ? memory.tags.map((tag: string) => <Badge key={tag}>{tag}</Badge>) : <span className="text-sm text-muted-foreground">—</span>}
                    </div>
                  </div>
                </div>

                <div className="grid gap-3 border-t border-border pt-4 text-sm md:grid-cols-2">
                  <div>
                    <span className="text-muted-foreground">Created</span>
                    <span className="ml-2">{memory.created_at ? new Date(memory.created_at).toLocaleString() : "—"}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Last updated</span>
                    <span className="ml-2">{memory.updated_at ? new Date(memory.updated_at).toLocaleString() : "—"}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
            </div>
          ),
        },
        {
          label: "Entity Graph",
          content: (
          <Card>
            <CardHeader>
              <CardTitle>Entity Graph</CardTitle>
              <CardDescription>Visual representation of entities and their relationships extracted from memories.</CardDescription>
            </CardHeader>
            <CardContent>
              <EntityGraph nodes={[]} edges={[]} />
            </CardContent>
          </Card>
          ),
        },
      ]} />
    </div>
  );
}

import { Database, Gauge, KeyRound, Zap, Activity, ServerCog } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { requireSession } from "@/lib/auth-helpers";
import { getUsageAction, getMemoriesAction, listApiKeysAction, getAuditLogAction } from "@/app/actions";

export const revalidate = 30;

export default async function DashboardPage() {
  const session = await requireSession();
  const [usage, memories, keys, audit] = await Promise.all([
    getUsageAction(),
    getMemoriesAction("", 5),
    listApiKeysAction(),
    getAuditLogAction(10),
  ]);

  const metrics = [
    { label: "Stored memories", value: (usage?.total_memories ?? memories.length ?? 0).toString(), delta: "total stored", icon: Database },
    { label: "Observations", value: (usage?.observations ?? 0).toString(), delta: "this period", icon: Activity },
    { label: "Active keys", value: ((keys as any[])?.length ?? 0).toString(), delta: "API keys", icon: KeyRound },
    { label: "Plan", value: usage?.plan_name ?? "Builder", delta: usage?.plan_description ?? "Active", icon: Gauge },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
        <div>
          <Badge>Production overview</Badge>
          <h2 className="mt-3 text-2xl font-semibold">Memory control plane</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
            Monitor tenant memory volume, retrieval quality, and API key usage.
          </p>
        </div>
        <div className="rounded-md border border-border bg-card px-4 py-3 text-sm">
          <span className="text-muted-foreground">Logged in as</span>
          <span className="ml-3 font-medium">{session.user.email}</span>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        {metrics.map((metric) => {
          const Icon = metric.icon ?? Activity;
          return (
            <Card key={metric.label}>
              <CardContent className="flex min-h-36 flex-col justify-between p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm text-muted-foreground">{metric.label}</p>
                    <p className="mt-2 text-2xl font-semibold">{metric.value}</p>
                  </div>
                  <Icon className="h-5 w-5 text-muted-foreground" />
                </div>
                <div>
                  <p className="text-xs text-primary">{metric.delta}</p>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
        <Card>
          <CardHeader>
            <CardTitle>Recent Memories</CardTitle>
            <CardDescription>Latest extracted records from recent observations.</CardDescription>
          </CardHeader>
          <CardContent>
            {(memories as any[])?.length === 0 ? (
              <p className="text-sm text-muted-foreground">No memories yet. Ingest an observation to get started.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Title</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>State</TableHead>
                    <TableHead>Importance</TableHead>
                    <TableHead>Updated</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(memories as any[]).map((memory: any) => (
                    <TableRow key={memory.id}>
                      <TableCell className="font-medium">{memory.title ?? "Untitled"}</TableCell>
                      <TableCell>{memory.memory_type ?? memory.type ?? "—"}</TableCell>
                      <TableCell><Badge>{memory.memory_state ?? memory.state ?? "active"}</Badge></TableCell>
                      <TableCell>{typeof memory.importance === "number" ? memory.importance.toFixed(2) : "—"}</TableCell>
                      <TableCell className="text-muted-foreground">
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
              <p className="text-sm text-muted-foreground">No recent activity.</p>
            ) : (
              <div className="space-y-3">
                {(audit as any[]).slice(0, 10).map((entry: any, i: number) => (
                  <div className="flex items-start gap-3 text-sm" key={entry.id ?? i}>
                    <span className="mt-0.5 flex h-2 w-2 rounded-full bg-primary" />
                    <div className="flex-1">
                      <p className="text-foreground">{entry.action ?? entry.event ?? "Action"}</p>
                      <p className="text-xs text-muted-foreground">
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

      <div className="grid gap-4 xl:grid-cols-[0.75fr_1.25fr]">
        <Card>
          <CardHeader>
            <CardTitle>API Keys</CardTitle>
            <CardDescription>Overview of active API keys.</CardDescription>
          </CardHeader>
          <CardContent>
            {(keys as any[])?.length === 0 ? (
              <p className="text-sm text-muted-foreground">No API keys yet. Create one in the API keys page.</p>
            ) : (
              <div className="space-y-2">
                {(keys as any[]).map((key: any) => (
                  <div className="flex items-center justify-between rounded-md border border-border bg-background p-3 text-sm" key={key.id}>
                    <span className="font-medium">{key.name}</span>
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
              <div className="flex items-center gap-3 rounded-md border border-border bg-background p-3 text-sm" key={item}>
                <span className="flex h-6 w-6 items-center justify-center rounded-md bg-secondary font-mono text-xs">
                  {index + 1}
                </span>
                {item}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

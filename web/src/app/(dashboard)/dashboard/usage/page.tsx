import { getUsageAction, listApiKeysAction } from "@/app/actions";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { UsageChart } from "./usage-chart";

export const revalidate = 30;

export default async function UsagePage() {
  const [usage, keys] = await Promise.all([
    getUsageAction(),
    listApiKeysAction(),
  ]);

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Welcome Header */}
      <div className="border-b border-[var(--color-graphite)]/30 pb-6">
        <Badge>Usage</Badge>
        <h2 className="mt-3 text-2xl font-light tracking-tight text-[var(--color-ghost)]">Usage</h2>
        <p className="mt-1 text-sm font-light text-[var(--color-smoke)]">
          Current period usage and daily breakdown.
        </p>
      </div>

      {/* Metrics Grid */}
      <div className="grid gap-6 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Observations</CardTitle>
            <CardDescription>Current period</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-light tracking-tight text-[var(--color-ghost)] tabular-nums">{usage?.observations ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Retrievals</CardTitle>
            <CardDescription>Current period</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-light tracking-tight text-[var(--color-ghost)] tabular-nums">{usage?.retrievals ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Memory writes</CardTitle>
            <CardDescription>Total stored</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-light tracking-tight text-[var(--color-ghost)] tabular-nums">{usage?.memory_writes ?? 0}</p>
          </CardContent>
        </Card>
      </div>

      {/* Usage Chart Card */}
      <Card>
        <CardHeader>
          <CardTitle>Daily breakdown</CardTitle>
          <CardDescription>Observations per day for the current period.</CardDescription>
        </CardHeader>
        <CardContent>
          <UsageChart data={usage?.daily_usage ?? []} />
        </CardContent>
      </Card>

      {/* Table Card */}
      <Card>
        <CardHeader>
          <CardTitle>Usage by API key</CardTitle>
          <CardDescription>Breakdown across your active keys.</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Key name</TableHead>
                <TableHead>Prefix</TableHead>
                <TableHead>Observations</TableHead>
                <TableHead>Operations</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(keys ?? []).length === 0 ? (
                <TableRow>
                  <TableCell className="text-[var(--color-smoke)] text-center py-6 font-light" colSpan={4}>
                    No API keys found.
                  </TableCell>
                </TableRow>
              ) : (
                (keys ?? []).map((key: any) => (
                  <TableRow key={key.id} className="hover:bg-[var(--color-charcoal)]/30 transition-colors duration-200">
                    <TableCell className="font-normal text-[var(--color-ghost)]">{key.name}</TableCell>
                    <TableCell className="font-mono text-xs text-[var(--color-smoke)]">{key.prefix}...</TableCell>
                    <TableCell className="text-[var(--color-ghost)] font-light">{key.usage?.observations ?? 0}</TableCell>
                    <TableCell className="text-[var(--color-ghost)] font-light">{key.usage?.operations ?? 0}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

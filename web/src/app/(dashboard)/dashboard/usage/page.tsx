import { getUsageAction, listApiKeysAction } from "@/app/actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { UsageChart } from "./usage-chart";
import Link from "next/link";

export const revalidate = 30;

export default async function UsagePage() {
  const [usage, keys] = await Promise.all([
    getUsageAction(),
    listApiKeysAction(),
  ]);

  return (
    <div className="space-y-6">
      <div>
        <Badge>Usage & billing</Badge>
        <h2 className="mt-3 text-2xl font-semibold">Usage</h2>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
          Current period usage and daily breakdown.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Observations</CardTitle>
            <CardDescription>Current period</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">{usage?.observations ?? 0}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              of {usage?.observation_limit ?? "—"} limit
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Memory operations</CardTitle>
            <CardDescription>Stored + retrieved</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">{usage?.memory_operations ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Storage</CardTitle>
            <CardDescription>Total memories stored</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">{usage?.total_memories ?? 0}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Daily breakdown</CardTitle>
          <CardDescription>Observations per day for the current period.</CardDescription>
        </CardHeader>
        <CardContent>
          <UsageChart data={usage?.daily_usage ?? []} />
        </CardContent>
      </Card>

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
                  <TableCell className="text-muted-foreground" colSpan={4}>No API keys found.</TableCell>
                </TableRow>
              ) : (
                (keys ?? []).map((key: any) => (
                  <TableRow key={key.id}>
                    <TableCell className="font-medium">{key.name}</TableCell>
                    <TableCell className="font-mono text-xs">{key.prefix}...</TableCell>
                    <TableCell>{key.usage?.observations ?? 0}</TableCell>
                    <TableCell>{key.usage?.operations ?? 0}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Plan</CardTitle>
          <CardDescription>Your current subscription plan.</CardDescription>
        </CardHeader>
        <CardContent className="flex items-center justify-between">
          <div>
            <p className="text-lg font-semibold">{usage?.plan_name ?? "Builder"}</p>
            <p className="text-sm text-muted-foreground">
              {usage?.plan_description ?? "For solo developers and early agent apps."}
            </p>
          </div>
          <Link href="/dashboard/billing">
            <Button>Upgrade plan</Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

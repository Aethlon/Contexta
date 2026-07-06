import { getUsageAction, createCheckoutSessionAction, openCustomerPortalAction } from "@/app/actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Check } from "lucide-react";

export const revalidate = 30;

const plans = [
  {
    name: "Builder",
    price: "$29",
    description: "For solo developers and early agent apps.",
    features: ["100k observations / month", "2M stored memories", "1 region", "Email support"],
    value: "builder",
  },
  {
    name: "Scale",
    price: "$99",
    description: "For production apps with heavier retrieval traffic.",
    features: ["1M observations / month", "20M stored memories", "Priority workers", "EU or US primary region"],
    value: "scale",
    highlighted: true,
  },
  {
    name: "Dedicated",
    price: "$299+",
    description: "For teams that need dedicated capacity.",
    features: ["Dedicated heavy node pool", "Latency nodes in US, EU, Singapore", "Custom limits", "Architecture support"],
    value: "dedicated",
  },
];

export default async function BillingPage() {
  const usage = await getUsageAction();

  return (
    <div className="space-y-6">
      <div>
        <Badge>Billing</Badge>
        <h2 className="mt-3 text-2xl font-semibold">Billing & plan</h2>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
          Manage your subscription, view invoices, and update payment methods.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Current plan</CardTitle>
            <CardDescription>Active subscription</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{usage?.plan_name ?? "Builder"}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {usage?.plan_description ?? "For solo developers and early agent apps."}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Period usage</CardTitle>
            <CardDescription>This billing period</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{usage?.observations ?? 0}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              of {usage?.observation_limit ?? "—"} observations
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Storage used</CardTitle>
            <CardDescription>Total memories</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{usage?.total_memories ?? 0}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {plans.map((plan) => (
          <Card className={plan.highlighted ? "border-primary bg-accent/40" : ""} key={plan.name}>
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <CardTitle>{plan.name}</CardTitle>
                {plan.highlighted ? <Badge>Recommended</Badge> : null}
              </div>
              <div className="pt-4">
                <span className="text-4xl font-semibold">{plan.price}</span>
                <span className="ml-2 text-sm text-muted-foreground">per month</span>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <p className="text-sm leading-6 text-muted-foreground">{plan.description}</p>
              <div className="space-y-3">
                {plan.features.map((feature) => (
                  <div className="flex items-start gap-2 text-sm" key={feature}>
                    <Check className="mt-0.5 h-4 w-4 text-primary" />
                    <span>{feature}</span>
                  </div>
                ))}
              </div>
              <form action={createCheckoutSessionAction}>
                <input name="plan" type="hidden" value={plan.value} />
                <Button className="w-full" disabled={plan.name === (usage?.plan_name ?? "Builder")} type="submit">
                  {plan.name === (usage?.plan_name ?? "Builder") ? "Current plan" : "Upgrade"}
                </Button>
              </form>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Customer portal</CardTitle>
          <CardDescription>Manage invoices and payment methods.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form action={openCustomerPortalAction}>
            <Button type="submit">Open customer portal</Button>
          </form>
          <div>
            <h4 className="mb-2 text-sm font-medium">Invoices</h4>
            {(usage?.invoices ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">No invoices yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Amount</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(usage?.invoices ?? []).map((invoice: any, i: number) => (
                    <TableRow key={invoice.id ?? i}>
                      <TableCell>{invoice.date ? new Date(invoice.date).toLocaleDateString() : "—"}</TableCell>
                      <TableCell>{invoice.amount ?? "—"}</TableCell>
                      <TableCell>
                        <Badge>{invoice.status ?? "unknown"}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

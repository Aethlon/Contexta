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
    <div className="space-y-8 animate-fade-in">
      {/* Top Welcome Header */}
      <div className="border-b border-[var(--color-graphite)]/30 pb-6">
        <Badge>Billing</Badge>
        <h2 className="mt-3 text-2xl font-light tracking-tight text-[var(--color-ghost)]">Billing & plan</h2>
        <p className="mt-1 text-sm font-light text-[var(--color-smoke)]">
          Manage your subscription, view invoices, and update payment methods.
        </p>
      </div>

      {/* Metrics Row */}
      <div className="grid gap-6 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Current plan</CardTitle>
            <CardDescription>Active subscription</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-light text-[var(--color-ghost)]">{usage?.plan_name ?? "Builder"}</p>
            <p className="mt-1.5 text-xs font-light text-[var(--color-smoke)] leading-relaxed">
              {usage?.plan_description ?? "For solo developers and early agent apps."}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Period observations</CardTitle>
            <CardDescription>This billing period</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-light text-[var(--color-ghost)] tabular-nums">{usage?.observations ?? 0}</p>
            <p className="mt-1.5 text-xs font-light text-[var(--color-smoke)]">
              of {usage?.observation_limit ?? "—"} observations
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Storage used</CardTitle>
            <CardDescription>Total memories</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-light text-[var(--color-ghost)] tabular-nums">{usage?.total_memories ?? 0}</p>
          </CardContent>
        </Card>
      </div>

      {/* Plans Section */}
      <div className="grid gap-6 lg:grid-cols-3 pt-4">
        {plans.map((plan) => (
          <Card 
            className={`flex flex-col justify-between ${
              plan.highlighted 
                ? "border-[var(--color-ghost)]/80 shadow-[0_16px_36px_rgba(0,0,0,0.18),inset_0_1px_0_0_rgba(255,255,255,0.03)] bg-[var(--color-ash)]" 
                : "border-[var(--color-graphite)]/30"
            }`} 
            key={plan.name}
          >
            <div>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="text-base font-normal">{plan.name}</CardTitle>
                  {plan.highlighted ? <Badge className="bg-[var(--color-charcoal)] border-[var(--color-graphite)]">Recommended</Badge> : null}
                </div>
                <div className="pt-5 pb-1">
                  <span className="text-4xl font-light tracking-tight text-[var(--color-ghost)]">{plan.price}</span>
                  <span className="ml-2 text-xs font-light text-[var(--color-smoke)]">per month</span>
                </div>
              </CardHeader>
              <CardContent className="space-y-6">
                <p className="text-xs font-light text-[var(--color-smoke)] leading-relaxed">{plan.description}</p>
                <div className="space-y-3.5">
                  {plan.features.map((feature) => (
                    <div className="flex items-start gap-2.5 text-xs text-[var(--color-ghost)] font-light" key={feature}>
                      <Check className="mt-0.5 h-3.5 w-3.5 text-[var(--color-smoke)]" strokeWidth={1.2} />
                      <span>{feature}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </div>
            <CardContent className="pt-2">
              <form action={createCheckoutSessionAction}>
                <input name="plan" type="hidden" value={plan.value} />
                <Button 
                  className="w-full" 
                  disabled={plan.name === (usage?.plan_name ?? "Builder")} 
                  type="submit"
                  variant={plan.highlighted ? "default" : "secondary"}
                >
                  {plan.name === (usage?.plan_name ?? "Builder") ? "Current plan" : "Upgrade"}
                </Button>
              </form>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Customer Portal Section */}
      <Card>
        <CardHeader>
          <CardTitle>Customer portal</CardTitle>
          <CardDescription>Manage invoices and payment methods.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-8">
          <form action={openCustomerPortalAction}>
            <Button type="submit" variant="secondary">Open customer portal</Button>
          </form>
          
          <div className="space-y-4">
            <h4 className="text-xs font-mono tracking-widest uppercase text-[var(--color-smoke)] font-light">Invoice History</h4>
            {(usage?.invoices ?? []).length === 0 ? (
              <p className="text-sm font-light text-[var(--color-smoke)] py-4 text-center">No invoices yet.</p>
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
                    <TableRow key={invoice.id ?? i} className="hover:bg-[var(--color-charcoal)]/30 transition-colors duration-200">
                      <TableCell className="text-xs text-[var(--color-ghost)]">
                        {invoice.date ? new Date(invoice.date).toLocaleDateString() : "—"}
                      </TableCell>
                      <TableCell className="text-xs text-[var(--color-ghost)] font-light">
                        {invoice.amount ?? "—"}
                      </TableCell>
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

import Link from "next/link";
import {
  ArrowRight,
  Brain,
  Check,
  Gauge,
  Globe2,
  KeyRound,
  Network,
  ServerCog,
  Shield,
  Terminal,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const platform = [
  { icon: Brain, title: "Durable memory pipeline", text: "Observation intake, extraction, scoring, redaction, lifecycle decay, and retrieval feedback." },
  { icon: Network, title: "Hybrid context retrieval", text: "Semantic, keyword, graph, importance, and recency ranking for agent-ready context." },
  { icon: KeyRound, title: "Hosted key management", text: "Organization-scoped API keys are created through the contexta backend, not local browser state." },
  { icon: Shield, title: "Tenant isolation", text: "Shared-table multi-tenancy with organization boundaries in models, repositories, and API contracts." },
];

const pricing = [
  {
    name: "Builder",
    price: "$29",
    note: "per month",
    description: "For solo developers and early agent apps that need hosted memory without running pgvector, Redis, and workers.",
    features: ["100k observations / month", "2M stored memories", "1 region", "Email support"],
  },
  {
    name: "Scale",
    price: "$99",
    note: "per month",
    description: "For production apps with heavier retrieval traffic, background workers, and a tighter dashboard workflow.",
    features: ["1M observations / month", "20M stored memories", "Priority workers", "EU or US primary region"],
    highlighted: true,
  },
  {
    name: "Dedicated",
    price: "$299+",
    note: "per month",
    description: "For teams that need dedicated Hetzner capacity, low-latency worker nodes, and custom retention controls.",
    features: ["Dedicated heavy node pool", "Latency nodes in US, EU, Singapore", "Custom limits", "Architecture support"],
  },
];

const stats = [
  ["84 ms", "target p95 retrieval"],
  ["1 MB", "observation guardrail"],
  ["pgvector", "memory store"],
  ["Redis", "queue and cache"],
];

export default function HomePage() {
  return (
    <main className="min-h-screen">
      <section className="border-b border-border">
        <div className="mx-auto flex min-h-[92vh] max-w-7xl flex-col px-6 py-6">
          <nav className="flex items-center justify-between">
            <Link className="flex items-center gap-2 text-sm font-semibold" href="/">
              <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <Brain className="h-4 w-4" />
              </span>
              contexta
            </Link>
            <div className="flex items-center gap-2">
              <Button variant="ghost">
                <Link href="/sign-in">Sign in</Link>
              </Button>
              <Button>
                <Link className="flex items-center gap-2" href="/sign-up">
                  Create account <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            </div>
          </nav>

          <div className="grid flex-1 gap-10 py-14 lg:grid-cols-[1.02fr_0.98fr] lg:items-center">
            <div className="max-w-3xl space-y-7">
              <Badge>Hosted memory infrastructure for AI agents</Badge>
              <div className="space-y-5">
                <h1 className="text-5xl font-semibold tracking-normal text-foreground md:text-7xl">
                  contexta
                </h1>
                <p className="max-w-2xl text-lg leading-8 text-muted-foreground">
                  A production control plane for agent memory: ingest conversations,
                  extract durable facts, retrieve relevant context, and manage API
                  keys from a hosted dashboard.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Button>
                  <Link className="flex items-center gap-2" href="/sign-up">
                    Start with a paid plan <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button variant="outline">
                  <Link href="/dashboard/docs">Read setup docs</Link>
                </Button>
              </div>
              <div className="grid max-w-2xl grid-cols-2 gap-3 pt-4 md:grid-cols-4">
                {stats.map(([value, label]) => (
                  <div className="border-l border-border pl-3" key={label}>
                    <p className="font-mono text-lg text-foreground">{value}</p>
                    <p className="text-xs text-muted-foreground">{label}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-border bg-card p-4">
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-md border border-border bg-background p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">API gateway</span>
                    <Gauge className="h-4 w-4 text-primary" />
                  </div>
                  <p className="mt-4 text-3xl font-semibold">99.9%</p>
                  <p className="text-sm text-muted-foreground">target availability</p>
                </div>
                <div className="rounded-md border border-border bg-background p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Regions</span>
                    <Globe2 className="h-4 w-4 text-primary" />
                  </div>
                  <p className="mt-4 text-3xl font-semibold">3+</p>
                  <p className="text-sm text-muted-foreground">planned latency nodes</p>
                </div>
              </div>
              <pre className="mt-3 overflow-x-auto rounded-md border border-border bg-background p-4 font-mono text-xs leading-6 text-muted-foreground">
{`curl https://api.contexta.dev/observations \\
  -H "authorization: Bearer $CONTEXTA_API_KEY" \\
  -H "content-type: application/json" \\
  -d '{"messages":[{"role":"user","content":"Remember my stack."}]}'`}
              </pre>
              <div className="mt-3 rounded-md border border-border bg-background p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium">
                  <ServerCog className="h-4 w-4 text-primary" />
                  Backend stack
                </div>
                <div className="grid gap-2 text-sm text-muted-foreground md:grid-cols-2">
                  <span>FastAPI API</span>
                  <span>Celery workers</span>
                  <span>PostgreSQL + pgvector</span>
                  <span>Redis queues/cache</span>
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            {platform.map((feature) => (
              <Card key={feature.title}>
                <CardContent className="space-y-3 p-4">
                  <feature.icon className="h-5 w-5 text-primary" />
                  <div>
                    <h2 className="text-sm font-medium">{feature.title}</h2>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">{feature.text}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-border bg-background/65 px-6 py-16">
        <div className="mx-auto max-w-7xl">
          <div className="mb-8 max-w-2xl">
            <Badge>Pricing</Badge>
            <h2 className="mt-4 text-3xl font-semibold">Paid plans only, sized around real infrastructure.</h2>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              contexta runs stateful memory storage, embeddings, Redis-backed workers,
              and retrieval APIs. These starting prices are designed around a Hetzner
              dedicated-server base with room for regional worker nodes as usage grows.
            </p>
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            {pricing.map((plan) => (
              <Card className={plan.highlighted ? "border-primary bg-accent/40" : ""} key={plan.name}>
                <CardHeader>
                  <div className="flex items-center justify-between gap-3">
                    <CardTitle>{plan.name}</CardTitle>
                    {plan.highlighted ? <Badge>Most teams</Badge> : null}
                  </div>
                  <div className="pt-4">
                    <span className="text-4xl font-semibold">{plan.price}</span>
                    <span className="ml-2 text-sm text-muted-foreground">{plan.note}</span>
                  </div>
                </CardHeader>
                <CardContent className="space-y-5">
                  <p className="min-h-20 text-sm leading-6 text-muted-foreground">{plan.description}</p>
                  <div className="space-y-3">
                    {plan.features.map((feature) => (
                      <div className="flex items-start gap-2 text-sm" key={feature}>
                        <Check className="mt-0.5 h-4 w-4 text-primary" />
                        <span>{feature}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <section className="px-6 py-16">
        <div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <Badge>Developer Experience</Badge>
            <h2 className="mt-4 text-3xl font-semibold">A dashboard built for shipping agents.</h2>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              The hosted web app is no longer a local-only panel. It is shaped as
              an account dashboard where users create backend-synced keys, inspect
              memory health, and copy production-ready integration snippets.
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            {[
              ["API-first", "Dashboard mutations go through route handlers and the contexta API."],
              ["Clear setup", "Environment, observe, retrieve, and context flows are documented."],
              ["Operational view", "Usage, latency, workers, and region planning are first-class."],
            ].map(([title, text]) => (
              <div className="rounded-md border border-border bg-card p-4" key={title}>
                <Terminal className="mb-4 h-5 w-5 text-primary" />
                <h3 className="text-sm font-medium">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}

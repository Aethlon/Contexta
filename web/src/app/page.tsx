"use client";

import Link from "next/link";
import { ArrowRight, Brain, CheckCircle2, Code2, Github, Globe2, KeyRound, Network, Server, Shield, Sparkles, Terminal, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ThemeToggle } from "@/components/theme-toggle";
import { motion } from "framer-motion";

const springStiff = {
  type: "spring" as const,
  stiffness: 400,
  damping: 30,
};

const staggerContainer = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.08 },
  },
};

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: springStiff },
};

const features = [
  {
    icon: Brain,
    title: "Memory extraction",
    text: "Ingest conversations, extract durable facts, and let your agents reason with reliable context.",
  },
  {
    icon: Network,
    title: "Hybrid retrieval",
    text: "Blend semantic, keyword, graph, importance, and recency signals into one agent-ready response.",
  },
  {
    icon: KeyRound,
    title: "API key management",
    text: "Create scoped keys from the backend with tenant-safe controls and clean admin workflows.",
  },
  {
    icon: Shield,
    title: "Tenant isolation",
    text: "Every query is automatically scoped to the right organization without leaking cross-tenant state.",
  },
];

const quickstart = `# 1. Create an API key in the dashboard
# 2. Export your environment
export CONTEXTA_API_URL=http://localhost:8000
export CONTEXTA_API_KEY=mk_live_...

# 3. Send an observation
curl $CONTEXTA_API_URL/v1/observations \\
  -H "Authorization: Bearer $CONTEXTA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"user_id":"...","org_id":"...","messages":[{"role":"user","content":"I prefer python."}]}'

# 4. Retrieve context
curl -X POST $CONTEXTA_API_URL/v1/retrieve \\
  -H "Authorization: Bearer $CONTEXTA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"user_id":"...","query_text":"preferences"}'`;

const stats = [
  { value: "< 200ms", label: "median retrieval" },
  { value: "4x", label: "richer context" },
  { value: "100%", label: "tenant scoped" },
];

const steps = [
  { title: "Observe", desc: "Your agent sends conversation payloads to the gateway and they get validated instantly." },
  { title: "Extract", desc: "An LLM extracts facts, preferences, entities, and relationships into durable memory." },
  { title: "Retrieve", desc: "Hybrid search ranks the right context for every prompt and workflow." },
];

export default function HomePage() {
  return (
    <main className="relative min-h-screen overflow-hidden bg-[var(--color-abyss)] py-6">
      <div className="mx-auto max-w-6xl px-6 lg:px-8">
        {/* Navigation Bar */}
        <motion.nav
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={springStiff}
          className="flex items-center justify-between border-b border-[var(--color-graphite)]/30 pb-5"
        >
          <Link className="flex items-center gap-2.5 text-sm font-light text-[var(--color-ghost)]" href="/">
            <Brain className="h-5 w-5 text-[var(--color-smoke)]" strokeWidth={1.2} />
            <span className="text-base tracking-tight font-normal">contexta</span>
          </Link>
          <div className="flex items-center gap-6">
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener"
              className="flex items-center gap-1.5 text-sm text-[var(--color-smoke)] transition-colors hover:text-[var(--color-ghost)] font-light"
            >
              <Github className="h-4 w-4" strokeWidth={1.2} /> GitHub
            </a>
            <ThemeToggle />
            <Link href="/sign-in" className="text-sm text-[var(--color-smoke)] hover:text-[var(--color-ghost)] transition-colors font-light">
              Sign in
            </Link>
            <Button variant="default">
              <Link href="/sign-up" className="flex items-center gap-1">
                Get started <ArrowRight className="h-4 w-4" strokeWidth={1.2} />
              </Link>
            </Button>
          </div>
        </motion.nav>

        {/* Hero Section */}
        <motion.section
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-100px" }}
          variants={staggerContainer}
          className="grid gap-16 py-20 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:py-32"
        >
          <div className="space-y-8">
            <motion.div variants={fadeUp} className="inline-flex items-center">
              <Badge className="text-xs">
                <Sparkles className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.2} /> Open source memory layer for AI agents
              </Badge>
            </motion.div>
            <motion.h1
              variants={fadeUp}
              className="text-5xl font-light leading-[1.05] tracking-tighter sm:text-6xl lg:text-7xl text-[var(--color-ghost)]"
            >
              Give your agents
              <br />
              <span className="text-[var(--color-smoke)]">a durable memory.</span>
            </motion.h1>
            <motion.p variants={fadeUp} className="max-w-xl text-lg font-light leading-8 text-[var(--color-smoke)]">
              Contexta turns raw conversations into structured, durable memory so your products can reason,
              personalize, and stay grounded over time.
            </motion.p>
            <motion.div variants={fadeUp} className="flex flex-wrap gap-4">
              <Button variant="default">
                <Link href="/sign-up" className="flex items-center gap-1.5">
                  Create free account <ArrowRight className="h-4 w-4" strokeWidth={1.2} />
                </Link>
              </Button>
              <Button variant="secondary">
                <Link href="/dashboard/docs">View docs</Link>
              </Button>
            </motion.div>
            <motion.div variants={fadeUp} className="flex flex-wrap gap-5 text-xs font-mono tracking-widest uppercase text-[var(--color-smoke)] pt-4">
              <span className="flex items-center gap-2"><Zap className="h-3.5 w-3.5" strokeWidth={1.2} /> FastAPI + Celery</span>
              <span className="flex items-center gap-2"><Server className="h-3.5 w-3.5" strokeWidth={1.2} /> PostgreSQL + pgvector</span>
              <span className="flex items-center gap-2"><Globe2 className="h-3.5 w-3.5" strokeWidth={1.2} /> OpenAI & DeepSeek</span>
            </motion.div>
          </div>

          {/* Interactive Code Preview */}
          <motion.div variants={fadeUp} className="relative">
            <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-0 shadow-[0_24px_50px_rgba(0,0,0,0.2)]">
              <div className="flex items-center justify-between border-b border-[var(--color-graphite)]/30 px-6 py-4">
                <div className="flex gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-graphite)]" />
                  <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-graphite)]" />
                  <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-graphite)]" />
                </div>
                <span className="text-xs font-mono tracking-widest uppercase text-[var(--color-smoke)]">memory-preview</span>
              </div>
              <CardContent className="p-6 space-y-6">
                <pre className="overflow-x-auto rounded-xl bg-[var(--color-abyss)] p-4 font-mono text-[11px] leading-6 text-[var(--color-smoke)] border border-[var(--color-graphite)]/20">
                  {quickstart}
                </pre>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-4">
                    <div className="flex items-center gap-2 text-xs font-mono tracking-widest uppercase text-[var(--color-smoke)]">
                      <Code2 className="h-4 w-4" strokeWidth={1.2} /> Structured facts
                    </div>
                    <div className="mt-3 text-3xl font-light text-[var(--color-ghost)]">12</div>
                    <p className="mt-1 text-xs text-[var(--color-smoke)] font-light">preferences, constraints, and relationships extracted.</p>
                  </div>
                  <div className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-4">
                    <div className="flex items-center gap-2 text-xs font-mono tracking-widest uppercase text-[var(--color-smoke)]">
                      <Terminal className="h-4 w-4" strokeWidth={1.2} /> Retrieval ready
                    </div>
                    <p className="mt-3 text-xs text-[var(--color-smoke)] font-light leading-relaxed">
                      The API returns ranked context for your agents in a single call.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        </motion.section>

        {/* Stats Section */}
        <motion.section
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-100px" }}
          variants={staggerContainer}
          className="grid gap-8 sm:grid-cols-3 border-t border-[var(--color-graphite)]/30 py-16"
        >
          {stats.map((stat) => (
            <motion.div key={stat.label} variants={fadeUp} className="text-center sm:text-left py-4">
              <div className="text-4xl font-light text-[var(--color-ghost)] tracking-tight">{stat.value}</div>
              <div className="mt-2 text-xs font-mono tracking-widest uppercase text-[var(--color-smoke)]">{stat.label}</div>
            </motion.div>
          ))}
        </motion.section>

        {/* Features Bento Grid */}
        <motion.section
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-100px" }}
          variants={staggerContainer}
          className="grid gap-8 md:grid-cols-2 lg:grid-cols-4 py-20"
        >
          {features.map((feature) => (
            <motion.div key={feature.title} variants={fadeUp}>
              <Card className="h-full border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] hover:border-[var(--color-smoke)]/40 transition-colors duration-300">
                <CardContent className="space-y-4 p-6">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-charcoal)] text-[var(--color-ghost)]">
                    <feature.icon className="h-5 w-5" strokeWidth={1.2} />
                  </div>
                  <div>
                    <h3 className="text-base font-normal text-[var(--color-ghost)]">{feature.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-[var(--color-smoke)] font-light">{feature.text}</p>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.section>

        {/* Architecture Section */}
        <motion.section
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-100px" }}
          variants={staggerContainer}
          className="border-t border-[var(--color-graphite)]/30 py-24 lg:py-32"
        >
          <div className="grid gap-16 lg:grid-cols-[0.8fr_1.2fr]">
            <div className="space-y-6">
              <Badge className="text-xs">Architecture</Badge>
              <h2 className="text-3xl font-light tracking-tight sm:text-4xl text-[var(--color-ghost)]">
                Built for fast, reliable memory workflows.
              </h2>
              <p className="text-base leading-7 text-[var(--color-smoke)] font-light">
                A polyglot stack designed to ingest, extract, and retrieve memory with the stability your agents need.
              </p>
              <div className="space-y-4 pt-4">
                {[
                  "FastAPI gateway for every request",
                  "Async extraction workers for durable memory",
                  "PostgreSQL + pgvector for reliable retrieval",
                  "Tenant-safe retrieval from the first request",
                ].map((item) => (
                  <div key={item} className="flex items-center gap-3 text-sm text-[var(--color-ghost)] font-light">
                    <CheckCircle2 className="h-4 w-4 text-[var(--color-smoke)]" strokeWidth={1.2} />
                    {item}
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-2xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6 shadow-[0_16px_36px_rgba(0,0,0,0.15)] space-y-6">
              <div className="grid gap-4 md:grid-cols-3">
                {steps.map((item) => (
                  <div key={item.title} className="rounded-xl border border-[var(--color-graphite)]/20 bg-[var(--color-abyss)] p-4">
                    <div className="text-xs font-mono tracking-widest uppercase text-[var(--color-ghost)]">{item.title}</div>
                    <p className="mt-2 text-xs leading-5 text-[var(--color-smoke)] font-light">{item.desc}</p>
                  </div>
                ))}
              </div>
              <div className="rounded-xl border border-[var(--color-graphite)]/20 bg-[var(--color-abyss)] p-4 overflow-x-auto">
                <pre className="font-mono text-[10px] leading-5 text-[var(--color-smoke)]">
{`POST /v1/observations      POST /v1/retrieve      GET /v1/memories
      │                           │                      │
      ▼                           ▼                      ▼
┌──────────────┐        ┌──────────────────────┐      ┌──────────────────┐
│  FastAPI     │ ─────▶ │  Celery Worker       │ ───▶ │  PostgreSQL      │
│  Gateway     │        │  LLM Extraction      │      │  + pgvector      │
└──────────────┘        │  Entity Resolution   │      │  + Redis cache   │
                        │  Deduplication       │      └──────────────────┘
                        └──────────────────────┘`}
                </pre>
              </div>
            </div>
          </div>
        </motion.section>

        {/* Footer */}
        <motion.footer
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="border-t border-[var(--color-graphite)]/30 pt-10 pb-6"
        >
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-2.5 text-xs font-light text-[var(--color-smoke)]">
              <Brain className="h-4 w-4" strokeWidth={1.2} />
              <span>contexta — memory intelligence for AI agents</span>
            </div>
            <div className="flex flex-wrap gap-6 text-xs text-[var(--color-smoke)] font-light">
              <Link href="/sign-in" className="transition-colors hover:text-[var(--color-ghost)]">Sign in</Link>
              <Link href="/sign-up" className="transition-colors hover:text-[var(--color-ghost)]">Sign up</Link>
              <a href="https://github.com" target="_blank" rel="noopener" className="transition-colors hover:text-[var(--color-ghost)]">GitHub</a>
            </div>
          </div>
        </motion.footer>
      </div>
    </main>
  );
}

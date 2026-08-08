"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Brain, Check, Copy, Github, KeyRound, Network, Shield, Sparkles, Terminal, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { ThemeToggle } from "@/components/theme-toggle";
import { motion, AnimatePresence } from "framer-motion";

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
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: springStiff },
};

const GITHUB_REPO = "https://github.com/Aethlon/Contexta";

const quickstartSnippets = {
  curl: `curl ${GITHUB_REPO.replace("github.com", "api.github.com")}/v1/observations \\
  -H "Authorization: Bearer $CONTEXTA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "user_id": "usr_9102",
    "messages": [{"role": "user", "content": "I prefer python."}]
  }'`,
  python: `from contexta import Contexta

client = Contexta(api_key="mk_live_...")
client.observe(
    user_id="usr_9102",
    messages=[{"role": "user", "content": "I prefer python."}]
)`,
  javascript: `import { Contexta } from "contexta-node";

const client = new Contexta({ apiKey: "mk_live_..." });
await client.observe({
  userId: "usr_9102",
  messages: [{ role: "user", content: "I prefer python." }]
});`,
};

const mockObservations = [
  {
    input: "I prefer working in Python and using dark mode.",
    facts: [
      { key: "language", value: "Python", confidence: 0.99 },
      { key: "ui_preference", value: "dark_mode", confidence: 0.95 }
    ]
  },
  {
    input: "Remember that Aethlon is located in San Francisco.",
    facts: [
      { key: "company", value: "Aethlon", confidence: 0.98 },
      { key: "location", value: "San Francisco", confidence: 0.92 }
    ]
  },
  {
    input: "I am the CTO of Contexta. I use VS Code.",
    facts: [
      { key: "role", value: "CTO", confidence: 0.97 },
      { key: "editor", value: "VS Code", confidence: 0.99 },
      { key: "organization", value: "Contexta", confidence: 0.96 }
    ]
  }
];

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<"curl" | "python" | "javascript">("curl");
  const [copied, setCopied] = useState(false);
  const [demoIndex, setDemoIndex] = useState(0);
  const [demoInput, setDemoInput] = useState(mockObservations[0].input);
  const [isProcessing, setIsProcessing] = useState(false);
  const [extractedFacts, setExtractedFacts] = useState<any[]>(mockObservations[0].facts);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(quickstartSnippets[activeTab]);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRunDemo = () => {
    setIsProcessing(true);
    setTimeout(() => {
      setExtractedFacts(mockObservations[demoIndex].facts);
      setIsProcessing(false);
    }, 800);
  };

  const selectDemoObservation = (idx: number) => {
    setDemoIndex(idx);
    setDemoInput(mockObservations[idx].input);
    setIsProcessing(true);
    setTimeout(() => {
      setExtractedFacts(mockObservations[idx].facts);
      setIsProcessing(false);
    }, 600);
  };

  return (
    <main className="relative min-h-screen bg-[var(--color-abyss)] py-6 overflow-x-hidden selection:bg-[var(--color-charcoal)] selection:text-[var(--color-ghost)]">
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
              href={GITHUB_REPO}
              target="_blank"
              rel="noopener noreferrer"
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
          className="flex flex-col items-center text-center py-20 lg:py-32 space-y-8"
        >
          <motion.div variants={fadeUp}>
            <Badge className="text-xs lowercase bg-[var(--color-ash)] border-[var(--color-graphite)]/50 text-[var(--color-smoke)] font-mono">
              <Sparkles className="mr-1.5 h-3 w-3 text-[var(--color-smoke)]" strokeWidth={1.2} /> v0.2.0 • open source memory layer
            </Badge>
          </motion.div>
          <motion.h1
            variants={fadeUp}
            className="text-5xl font-light leading-[1.05] tracking-tighter sm:text-7xl lg:text-8xl text-[var(--color-ghost)] max-w-4xl"
          >
            The memory plane for <br />
            <span className="text-[var(--color-smoke)]">AI agent architectures.</span>
          </motion.h1>
          <motion.p
            variants={fadeUp}
            className="max-w-xl text-lg font-light leading-8 text-[var(--color-smoke)]"
          >
            Contexta parses multi-turn chat logs into structured, graph-relational entities. Keep your copilots, assistants, and production agents permanently grounded.
          </motion.p>
          <motion.div variants={fadeUp} className="flex flex-wrap gap-4 justify-center">
            <Button variant="default" className="h-11 px-6 text-sm">
              <Link href="/sign-up" className="flex items-center gap-1.5">
                Deploy free instance <ArrowRight className="h-4 w-4" strokeWidth={1.2} />
              </Link>
            </Button>
            <a href={GITHUB_REPO} target="_blank" rel="noopener noreferrer">
              <Button variant="secondary" className="h-11 px-6 text-sm flex items-center gap-2">
                <Github className="h-4 w-4" strokeWidth={1.2} /> Star on GitHub
              </Button>
            </a>
          </motion.div>
        </motion.section>

        {/* Interactive Live Extraction Playground */}
        <motion.section
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true }}
          variants={staggerContainer}
          className="py-12"
        >
          <motion.div variants={fadeUp} className="space-y-4 text-center max-w-2xl mx-auto mb-12">
            <h2 className="text-2xl font-light text-[var(--color-ghost)] tracking-tight">Interactive Memory Playground</h2>
            <p className="text-sm font-light text-[var(--color-smoke)]">
              Select a conversational payload below and watch contexta extract durable, graph-relational memory facts in real-time.
            </p>
          </motion.div>

          <motion.div variants={fadeUp}>
            <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] overflow-hidden shadow-[0_24px_50px_rgba(0,0,0,0.15)]">
              <div className="grid md:grid-cols-[0.9fr_1.1fr] divide-y md:divide-y-0 md:divide-x divide-[var(--color-graphite)]/20">
                
                {/* Left Controller Panel */}
                <div className="p-6 space-y-6">
                  <div className="space-y-2">
                    <Label>Select Observation Template</Label>
                    <div className="flex flex-col gap-2">
                      {mockObservations.map((obs, idx) => (
                        <button
                          key={idx}
                          onClick={() => selectDemoObservation(idx)}
                          className={`text-left p-3.5 rounded-xl border text-xs font-light transition-all select-none ${
                            demoIndex === idx
                              ? "bg-[var(--color-charcoal)] border-[var(--color-ghost)]/40 text-[var(--color-ghost)] font-normal"
                              : "bg-[var(--color-abyss)] border-[var(--color-graphite)]/30 text-[var(--color-smoke)] hover:border-[var(--color-smoke)]/40"
                          }`}
                        >
                          &ldquo;{obs.input}&rdquo;
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-2 flex flex-col">
                    <Label htmlFor="demo-input">Agent Observation Payload</Label>
                    <textarea
                      id="demo-input"
                      value={demoInput}
                      onChange={(e) => setDemoInput(e.target.value)}
                      rows={3}
                      className="w-full rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-abyss)] p-3 text-xs font-light text-[var(--color-ghost)] outline-none focus:border-[var(--color-smoke)]/50 resize-none transition-colors"
                    />
                  </div>

                  <Button onClick={handleRunDemo} className="w-full h-10 text-xs flex items-center justify-center gap-1.5" disabled={isProcessing}>
                    <Zap size={14} className="text-[var(--color-smoke)]" strokeWidth={1.2} /> Ingest Observation
                  </Button>
                </div>

                {/* Right Result Terminal */}
                <div className="bg-[var(--color-abyss)] p-6 flex flex-col justify-between min-h-[300px]">
                  <div className="space-y-4">
                    <div className="flex items-center justify-between border-b border-[var(--color-graphite)]/30 pb-3">
                      <span className="text-[10px] font-mono tracking-widest uppercase text-[var(--color-smoke)] flex items-center gap-1.5">
                        <Terminal size={12} strokeWidth={1.2} /> Extraction Gateway output
                      </span>
                      {isProcessing ? (
                        <span className="flex h-1.5 w-1.5 rounded-full bg-[var(--color-smoke)] animate-ping" />
                      ) : (
                        <Badge className="bg-[var(--color-ash)] text-[var(--color-smoke)] lowercase font-mono px-2 py-0.5">synced</Badge>
                      )}
                    </div>

                    <div className="space-y-3 min-h-[160px] flex flex-col justify-center">
                      {isProcessing ? (
                        <div className="flex flex-col items-center justify-center gap-2 py-8">
                          <span className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--color-smoke)] border-t-transparent" />
                          <span className="text-xs font-mono tracking-widest text-[var(--color-smoke)] uppercase">Extracting facts...</span>
                        </div>
                      ) : (
                        <div className="space-y-2">
                          <AnimatePresence mode="popLayout">
                            {extractedFacts.map((fact, idx) => (
                              <motion.div
                                key={fact.key + idx}
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: 10 }}
                                transition={springStiff}
                                className="flex items-center justify-between rounded-xl border border-[var(--color-graphite)]/20 bg-[var(--color-ash)]/50 p-3 text-xs"
                              >
                                <div className="flex items-center gap-2">
                                  <code className="text-xs font-mono text-[var(--color-smoke)]">{fact.key}</code>
                                  <span className="text-[var(--color-smoke)]">→</span>
                                  <span className="text-[var(--color-ghost)] font-normal">{fact.value}</span>
                                </div>
                                <div className="flex items-center gap-2 text-[10px] font-mono text-[var(--color-smoke)]">
                                  <span>confidence:</span>
                                  <span>{fact.confidence.toFixed(2)}</span>
                                </div>
                              </motion.div>
                            ))}
                          </AnimatePresence>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="text-[10px] font-mono tracking-wider text-[var(--color-smoke)] border-t border-[var(--color-graphite)]/20 pt-4 flex justify-between items-center">
                    <span>observation pipeline active</span>
                    <span>api response: 200 OK</span>
                  </div>
                </div>

              </div>
            </Card>
          </motion.div>
        </motion.section>

        {/* Bento Grid Features Section */}
        <motion.section
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-100px" }}
          variants={staggerContainer}
          className="grid gap-6 md:grid-cols-6 py-20"
        >
          {/* Feature 1 - Left Wide Card */}
          <motion.div variants={fadeUp} className="md:col-span-4">
            <Card className="h-full border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-8 flex flex-col justify-between">
              <div className="space-y-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-charcoal)] text-[var(--color-ghost)]">
                  <Brain className="h-5 w-5" strokeWidth={1.2} />
                </div>
                <h3 className="text-lg font-normal text-[var(--color-ghost)]">Graph-relational facts extraction</h3>
                <p className="text-sm font-light text-[var(--color-smoke)] leading-relaxed max-w-xl">
                  Contexta doesn&apos;t just store raw logs. Our LLM-powered extraction engine identifies preferences, temporal states, and organization connections, linking them in a durable Postgres relational memory graph.
                </p>
              </div>
              <div className="pt-6 font-mono text-[10px] tracking-widest uppercase text-[var(--color-smoke)]">
                auto-deduplication enabled
              </div>
            </Card>
          </motion.div>

          {/* Feature 2 - Right Narrow Card */}
          <motion.div variants={fadeUp} className="md:col-span-2">
            <Card className="h-full border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-8 flex flex-col justify-between">
              <div className="space-y-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-charcoal)] text-[var(--color-ghost)]">
                  <Network className="h-5 w-5" strokeWidth={1.2} />
                </div>
                <h3 className="text-lg font-normal text-[var(--color-ghost)]">Hybrid retrieval</h3>
                <p className="text-sm font-light text-[var(--color-smoke)] leading-relaxed">
                  Combine vector embeddings with keyword (BM25) and entity graph search in a single ranked query response.
                </p>
              </div>
              <div className="pt-6 font-mono text-[10px] tracking-widest uppercase text-[var(--color-smoke)]">
                median latency &lt; 200ms
              </div>
            </Card>
          </motion.div>

          {/* Feature 3 - Left Narrow Card */}
          <motion.div variants={fadeUp} className="md:col-span-2">
            <Card className="h-full border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-8 flex flex-col justify-between">
              <div className="space-y-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-charcoal)] text-[var(--color-ghost)]">
                  <Shield className="h-5 w-5" strokeWidth={1.2} />
                </div>
                <h3 className="text-lg font-normal text-[var(--color-ghost)]">Tenant-scoped isolation</h3>
                <p className="text-sm font-light text-[var(--color-smoke)] leading-relaxed">
                  Strict database and schema-level division. Rest assured that no tenant-scope data leaks into other requests.
                </p>
              </div>
              <div className="pt-6 font-mono text-[10px] tracking-widest uppercase text-[var(--color-smoke)]">
                enterprise grade
              </div>
            </Card>
          </motion.div>

          {/* Feature 4 - Right Wide Card */}
          <motion.div variants={fadeUp} className="md:col-span-4">
            <Card className="h-full border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-8 flex flex-col justify-between">
              <div className="space-y-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-charcoal)] text-[var(--color-ghost)]">
                  <KeyRound className="h-5 w-5" strokeWidth={1.2} />
                </div>
                <h3 className="text-lg font-normal text-[var(--color-ghost)]">Scoped API key manager</h3>
                <p className="text-sm font-light text-[var(--color-smoke)] leading-relaxed max-w-xl">
                  Allow developers to generate scoped write-only (observe) or read-only (retrieve) access tokens. Implement clean admin control pipelines across your organizations.
                </p>
              </div>
              <div className="pt-6 font-mono text-[10px] tracking-widest uppercase text-[var(--color-smoke)]">
                developer console ready
              </div>
            </Card>
          </motion.div>
        </motion.section>

        {/* Integration Quickstart Console */}
        <motion.section
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-100px" }}
          variants={staggerContainer}
          className="border-t border-[var(--color-graphite)]/30 py-24"
        >
          <div className="grid gap-12 lg:grid-cols-[0.8fr_1.2fr]">
            <div className="space-y-6">
              <Badge className="text-xs">Integration</Badge>
              <h2 className="text-3xl font-light tracking-tight text-[var(--color-ghost)]">
                Three lines of code to connect agent memory.
              </h2>
              <p className="text-sm font-light text-[var(--color-smoke)] leading-relaxed">
                Connect your FastAPI, LangChain, or custom agent flow in seconds. Open-sourced under the MIT license.
              </p>
              <div className="flex gap-4 border-b border-[var(--color-graphite)]/20 pb-2">
                {(["curl", "python", "javascript"] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`relative cursor-pointer text-xs font-mono tracking-widest uppercase pb-2 select-none ${
                      activeTab === tab
                        ? "text-[var(--color-ghost)] font-normal"
                        : "text-[var(--color-smoke)] font-light hover:text-[var(--color-ghost)]"
                    }`}
                  >
                    {tab}
                    {activeTab === tab && (
                      <motion.div
                        layoutId="activeHeroTabIndicator"
                        className="absolute -bottom-[1px] left-0 right-0 h-[1.5px] bg-[var(--color-ghost)]"
                        transition={springStiff}
                      />
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Code Snippet Container */}
            <div className="relative rounded-2xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6 shadow-[0_16px_36px_rgba(0,0,0,0.12)]">
              <pre className="overflow-x-auto font-mono text-xs text-[var(--color-smoke)] leading-relaxed min-h-[160px] pb-4">
                {quickstartSnippets[activeTab]}
              </pre>
              <Button
                variant="ghost"
                onClick={handleCopy}
                className="absolute right-4 top-4 h-8 w-8 p-0 rounded-lg hover:bg-[var(--color-charcoal)]"
              >
                {copied ? (
                  <Check className="h-4 w-4 text-[var(--color-smoke)]" strokeWidth={1.2} />
                ) : (
                  <Copy className="h-4 w-4 text-[var(--color-smoke)]" strokeWidth={1.2} />
                )}
              </Button>
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
              <span>contexta — open-source memory engine</span>
            </div>
            <div className="flex flex-wrap gap-6 text-xs text-[var(--color-smoke)] font-light">
              <a href={GITHUB_REPO} target="_blank" rel="noopener noreferrer" className="transition-colors hover:text-[var(--color-ghost)]">GitHub</a>
              <Link href="/sign-in" className="transition-colors hover:text-[var(--color-ghost)]">Sign in</Link>
              <Link href="/sign-up" className="transition-colors hover:text-[var(--color-ghost)]">Sign up</Link>
            </div>
          </div>
        </motion.footer>

      </div>
    </main>
  );
}

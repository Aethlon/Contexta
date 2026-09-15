"use client";

import React, { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

interface Fact {
  subject: string;
  predicate: string;
  object: string;
  category: string;
  confidence: number;
}

interface Scenario {
  title: string;
  input: string;
  facts: Fact[];
}

const SCENARIOS: Scenario[] = [
  {
    title: "Developer Stack & Preferences",
    input: "User prefers Rust over Go for systems code, utilizes Neovim in dark mode, and connects via Claude Desktop MCP tool.",
    facts: [
      { subject: "User", predicate: "prefers_language", object: "Rust (Systems)", category: "Preference", confidence: 0.99 },
      { subject: "User", predicate: "uses_editor", object: "Neovim", category: "Tooling", confidence: 0.98 },
      { subject: "User", predicate: "theme_preference", object: "Dark Mode", category: "UI", confidence: 0.99 },
      { subject: "User", predicate: "agent_protocol", object: "Claude Desktop MCP", category: "Integration", confidence: 0.96 },
    ],
  },
  {
    title: "Temporal Geo Relocation",
    input: "Notice: User has completed transfer from London HQ to Tokyo office. All meeting scheduling must shift to JST timezone.",
    facts: [
      { subject: "User", predicate: "current_office", object: "Tokyo HQ", category: "Active Geo", confidence: 0.99 },
      { subject: "User", predicate: "prior_office", object: "London [ARCHIVED]", category: "Temporal Decay", confidence: 0.95 },
      { subject: "User", predicate: "active_timezone", object: "Asia/Tokyo (JST)", category: "Scheduling", confidence: 0.99 },
    ],
  },
  {
    title: "Cluster Architecture Alert",
    input: "Performance benchmark: Upgraded vector index to pgvector HNSW M=16 efSearch=64. Recall latency reduced from 140ms down to 22ms.",
    facts: [
      { subject: "Cluster", predicate: "index_algorithm", object: "pgvector HNSW", category: "Infra", confidence: 0.99 },
      { subject: "Cluster", predicate: "p95_latency", object: "22ms (-84%)", category: "Telemetry", confidence: 0.98 },
      { subject: "Cluster", predicate: "isolation_policy", object: "Tenant Cryptographic Schema", category: "Security", confidence: 0.99 },
    ],
  },
];

export function ExtractionStudio() {
  const [scenarioIdx, setScenarioIdx] = useState(0);
  const [input, setInput] = useState(SCENARIOS[0].input);
  const [busy, setBusy] = useState(false);
  const [facts, setFacts] = useState<Fact[]>(SCENARIOS[0].facts);
  const [streamed, setStreamed] = useState(0);
  const timers = useRef<number[]>([]);

  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), []);

  const pick = (i: number) => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
    setScenarioIdx(i);
    setInput(SCENARIOS[i].input);
    setFacts(SCENARIOS[i].facts);
    setStreamed(SCENARIOS[i].facts.length);
    setBusy(false);
  };

  const run = () => {
    if (busy) return;
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
    setBusy(true);
    setFacts([]);
    setStreamed(0);
    const target = SCENARIOS[scenarioIdx].facts;
    target.forEach((f, i) => {
      const t = window.setTimeout(() => {
        setFacts((prev) => [...prev, f]);
        setStreamed(i + 1);
        if (i === target.length - 1) setBusy(false);
      }, 350 + i * 420);
      timers.current.push(t);
    });
  };

  return (
    <section id="playground" className="py-24 sm:py-32 border-t border-white/[0.04]">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-12 pb-8 border-b border-white/[0.04]">
        <div className="max-w-2xl">
          <div className="inline-flex items-center gap-2 mb-3 text-xs font-mono uppercase tracking-widest text-cyan-400">
            Live Extraction Studio
          </div>
          <h2 className="text-title text-2xl sm:text-4xl lg:text-5xl tracking-tight text-white leading-[1.15]">
            Real-time memory synthesis sandbox
          </h2>
        </div>
        <p className="text-sm font-light text-[#6B7280] max-w-xs leading-relaxed">
          Feed raw agent dialogue into the extraction engine and inspect relational triples. Fully client-side.
        </p>
      </div>

      <div className="rounded-3xl bg-white/[0.02] shadow-elev-2 overflow-hidden backdrop-blur-2xl grid grid-cols-1 lg:grid-cols-12">
        <div className="lg:col-span-5 p-6 sm:p-8 space-y-6 lg:border-r border-white/[0.05]">
          <div className="space-y-2">
            <span className="text-[11px] font-mono uppercase tracking-wider text-[#6B7280] block">Preset scenario</span>
            <div className="flex flex-wrap gap-2">
              {SCENARIOS.map((s, i) => (
                <button
                  key={s.title}
                  onClick={() => pick(i)}
                  className={`px-3.5 py-1.5 rounded-full text-xs font-mono transition-all ${
                    scenarioIdx === i ? "bg-blue-500/20 text-blue-300" : "bg-white/[0.03] text-[#6B7280] hover:text-white hover:bg-white/[0.06]"
                  }`}
                >
                  {s.title}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <span className="text-[11px] font-mono uppercase tracking-wider text-[#6B7280] block">Dialogue payload</span>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              rows={4}
              className="w-full rounded-2xl bg-black/40 p-3.5 text-xs font-light text-white outline-none focus:ring-2 focus:ring-blue-500/40 resize-none font-mono leading-relaxed"
              aria-label="Dialogue payload"
            />
          </div>

          <button
            onClick={run}
            disabled={busy}
            className="w-full py-3 rounded-full bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-xs font-mono uppercase tracking-wider text-white font-medium flex items-center justify-center gap-2 shadow-lg shadow-blue-600/25 transition-all"
          >
            <span className={busy ? "animate-spin inline-block" : "inline-block"} aria-hidden="true">{busy ? "◌" : "▸"}</span>
            <span>{busy ? `Synthesizing… ${streamed}/${SCENARIOS[scenarioIdx].facts.length}` : "Execute fact synthesis"}</span>
          </button>
          <p className="text-[11px] font-mono text-[#3D4450]">Simulated locally • no network • no API key needed</p>
        </div>

        <div className="lg:col-span-7 p-6 sm:p-8 bg-black/40 flex flex-col justify-between space-y-6">
          <div className="space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
              <span className="text-xs font-mono uppercase tracking-wider text-[#6B7280] flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                Extraction output
              </span>
              <span className="text-xs font-mono text-emerald-400">{busy ? "STREAMING…" : "200 OK • 38ms"}</span>
            </div>

            <div className="space-y-2.5 min-h-[180px]" aria-live="polite">
              <AnimatePresence mode="popLayout">
                {facts.map((f, idx) => (
                  <motion.div
                    key={`${f.predicate}-${idx}`}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.25 }}
                    className="p-3.5 rounded-xl bg-white/[0.03] flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs font-mono"
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 text-[10px]">{f.category}</span>
                      <span className="text-[#6B7280]">{f.subject}</span>
                      <span className="text-blue-400">→</span>
                      <span className="text-white font-medium">{f.predicate}:</span>
                      <span className="text-emerald-300 font-semibold">{f.object}</span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="inline-block w-16 h-1 rounded-full bg-white/[0.06] overflow-hidden" aria-hidden="true">
                        <motion.span
                          className="block h-full rounded-full bg-emerald-400"
                          initial={{ width: 0 }}
                          animate={{ width: `${Math.round(f.confidence * 100)}%` }}
                          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
                        />
                      </span>
                      <span className="text-[11px] text-[#6B7280]">
                        <span className="text-emerald-400">{Math.round(f.confidence * 100)}%</span>
                      </span>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
              {facts.length === 0 && (
                <div className="p-6 text-center text-xs font-mono text-[#3D4450]">
                  <span className="inline-block animate-pulse">▍</span> awaiting synthesis…
                </div>
              )}
            </div>
          </div>

          <div className="pt-3 border-t border-white/[0.06] flex items-center justify-between text-[11px] font-mono text-[#6B7280]">
            <span>INDEXED: POSTGRES HNSW GRAPH</span>
            <span>ZERO DRIFT VALIDATED</span>
          </div>
        </div>
      </div>
    </section>
  );
}

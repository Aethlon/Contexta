"use client";

import React from "react";
import { motion } from "framer-motion";

interface Strip {
  n: string;
  label: string;
  title: string;
  body: string;
  metric: string;
  diagram: React.ReactNode;
}

function TripleDiagram() {
  return (
    <svg viewBox="0 0 600 190" className="w-full h-[170px]" role="img" aria-label="Subject predicate object triple">
      <defs>
        <linearGradient id="capA" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#3B82F6" />
          <stop offset="100%" stopColor="#06B6D4" />
        </linearGradient>
      </defs>
      {[200, 400].map((x) => (
        <line key={x} x1={x} y1={95} x2={x + 60} y2={95} stroke="url(#capA)" strokeWidth={1.6} strokeDasharray="5 4">
          <animate attributeName="stroke-dashoffset" from="18" to="0" dur="1.2s" repeatCount="indefinite" />
        </line>
      ))}
      {[
        { x: 130, top: "SUBJECT", main: "User usr_9102", c: "#93C5FD" },
        { x: 330, top: "PREDICATE", main: "prefers_language", c: "#67E8F9" },
        { x: 520, top: "OBJECT", main: "Rust · 0.99", c: "#6EE7B7" },
      ].map((b, i) => (
        <g key={b.top}>
          <rect x={b.x - 88} y={52} width={176} height={86} rx={14} fill="rgba(255,255,255,0.03)" />
          <rect x={b.x - 88} y={52} width={176} height={86} rx={14} fill="none" stroke="rgba(255,255,255,0.07)" />
          <rect x={b.x - 88} y={52} width={176} height={10} rx={5} fill={b.c} opacity={0.35} transform={`translate(6,-4) skewX(-24)`} />
          <text x={b.x} y={80} textAnchor="middle" fontSize="9" fill="#3D4450" fontFamily="monospace" letterSpacing="2">{b.top}</text>
          <text x={b.x} y={104} textAnchor="middle" fontSize="12" fill="#fff" fontFamily="monospace">{b.main}</text>
          <motion.circle cx={b.x} cy={118} r={2.5} fill={b.c} initial={{ opacity: 0.4 }} whileInView={{ opacity: [0.4, 1, 0.4] }} viewport={{ once: false }} transition={{ duration: 2, repeat: Infinity, delay: i * 0.4 }} />
        </g>
      ))}
      <text x={300} y={168} textAnchor="middle" fontSize="10" fill="#3D4450" fontFamily="monospace">STATUS: REASONING COMPLETED</text>
    </svg>
  );
}

function TemporalDiagram() {
  return (
    <svg viewBox="0 0 600 150" className="w-full h-[130px]" role="img" aria-label="Temporal state transition">
      <line x1={60} y1={75} x2={540} y2={75} stroke="rgba(255,255,255,0.12)" strokeWidth={1.5} />
      <circle cx={150} cy={75} r={7} fill="none" stroke="#F87171" strokeWidth={1.6} opacity={0.8} />
      <text x={150} y={52} textAnchor="middle" fontSize="10" fill="#6B7280" fontFamily="monospace" textDecoration="line-through">London · 2024</text>
      <text x={150} y={104} textAnchor="middle" fontSize="9" fill="#F87171" fontFamily="monospace">ARCHIVED</text>
      <circle cx={450} cy={75} r={9} fill="#10B981">
        <animate attributeName="r" values="8;10;8" dur="2.4s" repeatCount="indefinite" />
      </circle>
      <text x={450} y={52} textAnchor="middle" fontSize="10" fill="#fff" fontFamily="monospace">Tokyo · Active</text>
      <text x={450} y={104} textAnchor="middle" fontSize="9" fill="#10B981" fontFamily="monospace">GROUNDED</text>
      <path d="M170 75 H 420" stroke="#10B981" strokeWidth={1.4} strokeDasharray="6 5" opacity={0.7}>
        <animate attributeName="stroke-dashoffset" from="22" to="0" dur="1s" repeatCount="indefinite" />
      </path>
    </svg>
  );
}

function EnclaveDiagram() {
  return (
    <svg viewBox="0 0 600 150" className="w-full h-[130px]" role="img" aria-label="Tenant enclave isolation">
      {[140, 300, 460].map((x, i) => (
        <g key={x}>
          <rect x={x - 62} y={34} width={124} height={82} rx={14} fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.08)" />
          <rect x={x - 62} y={34} width={124} height={12} rx={6} fill={i === 1 ? "rgba(59,130,246,0.5)" : "rgba(255,255,255,0.08)"} transform="translate(5,-3) skewX(-24)" />
          <circle cx={x - 40} cy={72} r={4} fill={["#10B981", "#3B82F6", "#8B5CF6"][i]} />
          <text x={x + 4} y={76} fontSize="10" fill="#D1D5DB" fontFamily="monospace">tenant_{["acme", "lc-prod", "cursor"][i]}</text>
          <text x={x} y={98} textAnchor="middle" fontSize="9" fill="#3D4450" fontFamily="monospace">AES-256 • ISOLATED</text>
        </g>
      ))}
      <line x1={202} y1={75} x2={238} y2={75} stroke="#EF4444" strokeWidth={1.4} strokeDasharray="3 4" />
      <text x={220} y={64} textAnchor="middle" fontSize="11" fill="#EF4444">✕</text>
      <line x1={362} y1={75} x2={398} y2={75} stroke="#EF4444" strokeWidth={1.4} strokeDasharray="3 4" />
      <text x={380} y={64} textAnchor="middle" fontSize="11" fill="#EF4444">✕</text>
    </svg>
  );
}

function RetrievalDiagram() {
  return (
    <svg viewBox="0 0 600 150" className="w-full h-[130px]" role="img" aria-label="Hybrid retrieval pipeline">
      {[
        { x: 120, t: "STAGE 1", m: "pgvector HNSW", c: "#93C5FD" },
        { x: 300, t: "STAGE 2", m: "BM25 Lexical", c: "#67E8F9" },
        { x: 480, t: "FUSION", m: "RRF Re-ranked", c: "#fff" },
      ].map((s, i) => (
        <g key={s.t}>
          <rect x={s.x - 78} y={38} width={156} height={74} rx={14} fill={i === 2 ? "rgba(59,130,246,0.12)" : "rgba(255,255,255,0.03)"} stroke={i === 2 ? "rgba(59,130,246,0.4)" : "rgba(255,255,255,0.07)"} />
          <text x={s.x} y={62} textAnchor="middle" fontSize="9" fill="#3D4450" fontFamily="monospace" letterSpacing="2">{s.t}</text>
          <text x={s.x} y={86} textAnchor="middle" fontSize="11" fill={s.c} fontFamily="monospace">{s.m}</text>
          {i < 2 && (
            <path d={`M${s.x + 78} 75 H ${s.x + 100}`} stroke="rgba(255,255,255,0.3)" strokeWidth={1.5}>
              <animate attributeName="opacity" values="0.3;1;0.3" dur="1.6s" repeatCount="indefinite" />
            </path>
          )}
        </g>
      ))}
    </svg>
  );
}

function LocalDiagram() {
  return (
    <div className="flex flex-wrap items-center gap-3 font-mono text-xs px-1 py-3">
      <span className="px-3 py-1.5 rounded-full bg-emerald-500/10 text-emerald-300">Local Ollama / vLLM</span>
      <span className="text-[#3D4450]">•</span>
      <span className="text-[#6B7280]">Qwen 2.5 7B quantized</span>
      <span className="text-[#3D4450]">•</span>
      <span className="text-[#6B7280]">FastEmbed ONNX</span>
      <span className="text-[#3D4450]">•</span>
      <span className="text-emerald-400">$0 inference</span>
    </div>
  );
}

function McpDiagram() {
  return (
    <div className="flex flex-wrap items-center gap-3 font-mono text-xs px-1 py-3">
      <span className="px-3 py-1.5 rounded-full bg-indigo-500/10 text-indigo-300">Cursor & Windsurf</span>
      <span className="text-[#3D4450]">•</span>
      <span className="text-[#6B7280]">Claude Desktop</span>
      <span className="text-[#3D4450]">•</span>
      <span className="text-[#6B7280]">LangChain / LlamaIndex</span>
      <span className="text-[#3D4450]">•</span>
      <span className="text-indigo-300">MCP 2.0 tools</span>
    </div>
  );
}

const STRIPS: Strip[] = [
  {
    n: "01",
    label: "ATOMIC FACT EXTRACTION",
    title: "Dialogue distilled to relational triples",
    body: "Conversational fluff, pleasantries, and greetings are purged. What remains are structured, immutable facts: (Subject • Predicate • Object) with confidence scores and temporal anchors.",
    metric: "99.4% Precision",
    diagram: <TripleDiagram />,
  },
  {
    n: "02",
    label: "TEMPORAL DYNAMICS",
    title: "Auto-conflict resolution",
    body: "When a user changes preference or relocates, Contexta marks superseded facts as historical and updates the active state without data loss.",
    metric: "Zero drift",
    diagram: <TemporalDiagram />,
  },
  {
    n: "03",
    label: "TENANT ISOLATION",
    title: "Strict enclave schemas",
    body: "Hard PostgreSQL schema boundaries per tenant. Zero cross-tenant bleeding, AES-256 at rest, SOC2 / GDPR posture.",
    metric: "AES-256",
    diagram: <EnclaveDiagram />,
  },
  {
    n: "04",
    label: "HYBRID RRF RETRIEVAL",
    title: "Vector + BM25 + graph traversal",
    body: "Single-paradigm vector search hallucinates on exact keywords. Contexta fuses dense cosine, BM25 lexical, and 2-hop graph spreading activation via RRF.",
    metric: "Sub-180ms",
    diagram: <RetrievalDiagram />,
  },
  {
    n: "05",
    label: "LOCAL ENGINE",
    title: "Zero data egress option",
    body: "Run extraction fully on-prem via quantized local Qwen 2.5 7B with FastEmbed ONNX. Zero cloud inference spend, zero context leaving your network.",
    metric: "$0 egress",
    diagram: <LocalDiagram />,
  },
  {
    n: "06",
    label: "AGENT ECOSYSTEM",
    title: "Model Context Protocol 2.0",
    body: "Plug-and-play MCP 2.0 server for Cursor, Windsurf, Claude Desktop, and LangChain / LlamaIndex agents with scoped observe / retrieve keys.",
    metric: "MCP 2.0",
    diagram: <McpDiagram />,
  },
];

export function CapabilityStrips() {
  return (
    <section id="capabilities" className="py-24 sm:py-32">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-12 pb-8 border-b border-white/[0.04]">
        <div className="max-w-2xl">
          <div className="inline-flex items-center gap-2 mb-3 text-xs font-mono uppercase tracking-widest text-purple-400">
            <span aria-hidden="true">✱</span> Architecture Capabilities
          </div>
          <h2 className="text-title text-2xl sm:text-4xl lg:text-5xl tracking-tight text-white leading-[1.15]">
            Engineered for stateful agent intelligence
          </h2>
        </div>
        <p className="text-sm font-light text-[#6B7280] max-w-xs leading-relaxed">
          Ditch fragile prompt-stuffing. Turnkey infrastructure for durable, verifiable long-term memory.
        </p>
      </div>

      <div className="space-y-5">
        {STRIPS.map((s, i) => (
          <motion.article
            key={s.n}
            className={`rounded-3xl p-7 sm:p-9 shadow-elev-1 backdrop-blur-xl grid gap-6 lg:grid-cols-12 lg:items-center ${
              i % 2 === 0 ? "bg-white/[0.02]" : "bg-white/[0.035]"
            }`}
            initial={{ opacity: 0, y: 28 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="lg:col-span-4 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#6B7280]">
                  {s.n} • {s.label}
                </span>
                <span className="text-[11px] font-mono px-2.5 py-0.5 rounded-full bg-white/[0.05] text-blue-300 whitespace-nowrap">
                  {s.metric}
                </span>
              </div>
              <h3 className="text-xl sm:text-2xl font-light text-white tracking-tight">{s.title}</h3>
              <p className="text-sm font-light text-[#6B7280] leading-relaxed">{s.body}</p>
            </div>
            <div className="lg:col-span-8 rounded-2xl bg-black/30 p-3 sm:p-5 overflow-hidden">
              {s.diagram}
            </div>
          </motion.article>
        ))}
      </div>
    </section>
  );
}

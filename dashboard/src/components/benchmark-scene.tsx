"use client";

import React, { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";

type Tab = "latency" | "throughput" | "accuracy";

const LATENCY = [
  { scale: "1K", contexta: 14, mem0: 45, langchain: 65 },
  { scale: "5K", contexta: 18, mem0: 72, langchain: 120 },
  { scale: "10K", contexta: 22, mem0: 110, langchain: 195 },
  { scale: "25K", contexta: 29, mem0: 165, langchain: 290 },
  { scale: "50K", contexta: 38, mem0: 240, langchain: 410 },
];

const THROUGHPUT = [
  { name: "Contexta", value: 2650, hot: true },
  { name: "Qdrant", value: 1420, hot: false },
  { name: "Weaviate", value: 850, hot: false },
  { name: "Pinecone", value: 420, hot: false },
  { name: "Mem0", value: 310, hot: false },
];

const ACCURACY = [
  { name: "Contexta Hybrid", value: 98.8, hot: true },
  { name: "Dense Vector", value: 81.4, hot: false },
  { name: "BM25 Lexical", value: 72.9, hot: false },
  { name: "Naive RAG", value: 64.2, hot: false },
];

const W = 720;
const H = 300;
const PL = 44;
const PR = 16;
const PT = 18;
const PB = 34;

function scaleLinear(domain: [number, number], range: [number, number]) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  return (v: number) => r0 + ((v - d0) / (d1 - d0 || 1)) * (r1 - r0);
}

function linePath(pts: { x: number; y: number }[]) {
  return pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

function areaPath(pts: { x: number; y: number }[], baseY: number) {
  const top = linePath(pts);
  const last = pts[pts.length - 1];
  const first = pts[0];
  return `${top} L${last.x.toFixed(1)},${baseY} L${first.x.toFixed(1)},${baseY} Z`;
}

function LatencyChart({ hover, setHover }: { hover: number | null; setHover: (i: number | null) => void }) {
  const maxY = 440;
  const x = scaleLinear([0, LATENCY.length - 1], [PL, W - PR]);
  const y = scaleLinear([0, maxY], [H - PB, PT]);
  const series = [
    { key: "contexta" as const, color: "#3B82F6", width: 2.6, glow: true, label: "Contexta Hybrid" },
    { key: "mem0" as const, color: "#F59E0B", width: 1.6, glow: false, label: "Mem0 Cloud" },
    { key: "langchain" as const, color: "#A855F7", width: 1.6, glow: false, label: "LangChain / Zep" },
  ];
  const pts = useMemo(
    () =>
      series.map((s) => ({
        ...s,
        p: LATENCY.map((d, i) => ({ x: x(i), y: y(d[s.key]) })),
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );
  const ticks = [0, 110, 220, 330, 440];
  return (
    <div>
      <div className="flex flex-wrap items-center gap-4 text-[11px] font-mono pb-3">
        {pts.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5" style={{ color: s.color }}>
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
        <span className="ml-auto text-[#3D4450]">lower is better • ms p95</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-[300px]" role="img" aria-label="P95 latency vs corpus scale">
        <defs>
          <linearGradient id="ctxFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3B82F6" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#3B82F6" stopOpacity="0" />
          </linearGradient>
          <filter id="ctxGlow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="4" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PL} x2={W - PR} y1={y(t)} y2={y(t)} stroke="rgba(255,255,255,0.06)" strokeDasharray="3 4" />
            <text x={PL - 8} y={y(t) + 4} textAnchor="end" fontSize="10" fill="#3D4450" fontFamily="monospace">
              {t}
            </text>
          </g>
        ))}
        {LATENCY.map((d, i) => (
          <text key={d.scale} x={x(i)} y={H - 12} textAnchor="middle" fontSize="11" fill="#6B7280" fontFamily="monospace">
            {d.scale}
          </text>
        ))}
        {/* isometric floor grid hint */}
        <g opacity="0.5">
          {LATENCY.map((_, i) => (
            <line key={i} x1={x(i)} x2={x(i) + 18} y1={H - PB} y2={H - PB - 10} stroke="rgba(255,255,255,0.05)" />
          ))}
        </g>
        <motion.path
          d={areaPath(pts[0].p, H - PB)}
          fill="url(#ctxFill)"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 1 }}
        />
        {pts.map((s) => (
          <motion.path
            key={s.key}
            d={linePath(s.p)}
            fill="none"
            stroke={s.color}
            strokeWidth={s.width}
            strokeLinecap="round"
            filter={s.glow ? "url(#ctxGlow)" : undefined}
            initial={{ pathLength: 0 }}
            whileInView={{ pathLength: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          />
        ))}
        {LATENCY.map((d, i) => (
          <g key={i}>
            <rect
              x={x(i) - 22}
              y={PT}
              width={44}
              height={H - PB - PT}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            />
            {hover === i && (
              <g>
                <line x1={x(i)} x2={x(i)} y1={PT} y2={H - PB} stroke="rgba(255,255,255,0.25)" />
                <circle cx={x(i)} cy={y(d.contexta)} r={5} fill="#3B82F6" stroke="#fff" strokeWidth={1.5} />
                <g>
                  <rect x={Math.min(x(i) + 10, W - 170)} y={PT + 6} width={160} height={64} rx={10} fill="#0F1016" opacity={0.96} />
                  <text x={Math.min(x(i) + 20, W - 160)} y={PT + 26} fontSize="10" fill="#6B7280" fontFamily="monospace">
                    SCALE {d.scale}
                  </text>
                  <text x={Math.min(x(i) + 20, W - 160)} y={PT + 42} fontSize="11" fill="#fff" fontFamily="monospace">
                    ctx {d.contexta}ms • mem0 {d.mem0}ms
                  </text>
                  <text x={Math.min(x(i) + 20, W - 160)} y={PT + 56} fontSize="11" fill="#A855F7" fontFamily="monospace">
                    zep {d.langchain}ms
                  </text>
                </g>
              </g>
            )}
          </g>
        ))}
      </svg>
      <p className="text-xs text-[#3D4450] font-light pt-1">HNSW M=16 efSearch=64 • pgvector • stable recall as corpus grows to 50K.</p>
    </div>
  );
}

function IsoBars({
  data,
  unit,
  max,
  hover,
  setHover,
}: {
  data: { name: string; value: number; hot: boolean }[];
  unit: string;
  max: number;
  hover: number | null;
  setHover: (i: number | null) => void;
}) {
  const bw = 420;
  const rowH = 52;
  const labelW = 150;
  return (
    <div className="space-y-1">
      {data.map((d, i) => {
        const pct = Math.max((d.value / max) * 100, 4);
        const active = hover === i;
        return (
          <div
            key={d.name}
            className="grid items-center gap-3 rounded-xl px-3 py-2 transition-colors"
            style={{
              gridTemplateColumns: `${labelW}px 1fr 92px`,
              background: active ? "rgba(255,255,255,0.04)" : "transparent",
            }}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          >
            <span className={`text-xs font-mono truncate ${d.hot ? "text-white" : "text-[#6B7280]"}`}>{d.name}</span>
            <div className="relative h-[26px]">
              {/* isometric block: top face + front face */}
              <div className="absolute inset-y-[5px] left-0 right-0 rounded-[4px] bg-white/[0.03]" />
              <motion.div
                className="absolute inset-y-[5px] left-0 rounded-[4px]"
                style={{
                  width: `${pct}%`,
                  background: d.hot
                    ? "linear-gradient(180deg, rgba(96,165,250,0.95), rgba(37,99,235,0.9))"
                    : "linear-gradient(180deg, rgba(255,255,255,0.14), rgba(255,255,255,0.06))",
                  boxShadow: d.hot ? "0 0 24px rgba(59,130,246,0.45), inset 0 1px 0 rgba(255,255,255,0.35)" : "inset 0 1px 0 rgba(255,255,255,0.08)",
                }}
                initial={{ width: 0 }}
                whileInView={{ width: `${pct}%` }}
                viewport={{ once: true }}
                transition={{ duration: 0.9, delay: i * 0.08, ease: [0.16, 1, 0.3, 1] }}
              />
              {/* top bevel to suggest isometric depth */}
              <motion.div
                className="absolute left-0 rounded-t-[4px]"
                style={{
                  top: 1,
                  height: 5,
                  width: `${pct}%`,
                  background: d.hot ? "rgba(191,219,254,0.5)" : "rgba(255,255,255,0.08)",
                  transform: "skewX(-32deg)",
                  transformOrigin: "left bottom",
                  marginLeft: 6,
                }}
                initial={{ opacity: 0 }}
                whileInView={{ opacity: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 0.6, delay: 0.2 + i * 0.08 }}
              />
            </div>
            <span className={`text-xs font-mono text-right ${d.hot ? "text-blue-300" : "text-[#6B7280]"}`}>
              {d.value.toLocaleString()} {unit}
            </span>
          </div>
        );
      })}
      <div className="hidden" style={{ width: bw, height: rowH * data.length }} />
    </div>
  );
}

export function BenchmarkScene() {
  const [tab, setTab] = useState<Tab>("latency");
  const [hover, setHover] = useState<number | null>(null);

  return (
    <section id="benchmarks" className="relative w-full py-24 sm:py-32 overflow-hidden bg-[#050507] select-none">
      <div className="absolute top-1/3 right-1/4 w-[700px] h-[350px] bg-blue-500/[0.025] rounded-full blur-[140px] pointer-events-none" />
      <div className="max-w-[1360px] mx-auto px-6 lg:px-12 relative">
        <motion.div
          className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-10 pb-8 border-b border-white/[0.04]"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 mb-3 text-xs font-mono uppercase tracking-widest text-blue-400">
              <span aria-hidden="true">✱</span> 50,000 Records Benchmark
            </div>
            <h2 className="text-title text-2xl sm:text-4xl lg:text-5xl tracking-tight text-white leading-[1.15]">
              Sub-180ms p95 recall at enterprise scale
            </h2>
            <p className="mt-3 text-sm text-[#6B7280] font-light max-w-xl leading-relaxed">
              Continuous multi-domain agent memory benchmark evaluating ingestion throughput,
              graph entity synthesis, and hybrid retrieval latency up to 50,000 records.
            </p>
          </div>
          <div className="flex items-center bg-white/[0.03] p-1 rounded-full" role="tablist" aria-label="Benchmark metric">
            {(["latency", "throughput", "accuracy"] as Tab[]).map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                onClick={() => { setTab(t); setHover(null); }}
                className={`px-4 py-1.5 text-xs font-mono rounded-full transition-all duration-200 ${
                  tab === t ? "bg-blue-500/20 text-blue-300" : "text-[#6B7280] hover:text-white"
                }`}
              >
                {t === "latency" ? "Recall Latency" : t === "throughput" ? "Throughput" : "Accuracy"}
              </button>
            ))}
          </div>
        </motion.div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {[
            { k: "P95 RECALL LATENCY", v: "38ms", s: "@ 50K", d: "6.3x faster than Mem0", c: "text-emerald-400" },
            { k: "INGESTION SPEED", v: "2,650", s: "rec/s", d: "Asyncpg batch pipeline", c: "text-blue-400" },
            { k: "HYBRID RECALL ACCURACY", v: "98.8%", s: "MRR@10", d: "+17.4% vs pure vector", c: "text-purple-400" },
            { k: "EGRESS COST OVERHEAD", v: "$0.00", s: "LOCAL", d: "Local Qwen 2.5 + ONNX", c: "text-cyan-400" },
          ].map((m, i) => (
            <motion.div
              key={m.k}
              className="p-4 rounded-2xl bg-white/[0.02] shadow-elev-1"
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: i * 0.08 }}
            >
              <div className="text-[11px] font-mono text-[#6B7280] uppercase">{m.k}</div>
              <div className="text-2xl sm:text-3xl font-light text-white mt-1 flex items-baseline gap-1.5">
                {m.v} <span className={`text-xs font-mono ${m.c}`}>{m.s}</span>
              </div>
              <div className={`text-[11px] font-mono mt-0.5 ${m.c}`}>{m.d}</div>
            </motion.div>
          ))}
        </div>

        <motion.div
          className="p-6 sm:p-8 rounded-3xl bg-white/[0.02] shadow-elev-2 backdrop-blur-xl"
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.8 }}
        >
          <AnimatePresence mode="wait">
            {tab === "latency" && (
              <motion.div key="latency" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.3 }}>
                <h3 className="text-lg font-normal text-white">P95 Retrieval Latency vs Memory Corpus Scale</h3>
                <p className="text-xs text-[#6B7280] font-light pb-4">Lower is better • hover any scale for exact values.</p>
                <LatencyChart hover={hover} setHover={setHover} />
              </motion.div>
            )}
            {tab === "throughput" && (
              <motion.div key="throughput" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.3 }}>
                <h3 className="text-lg font-normal text-white">Memory Record Ingestion Throughput</h3>
                <p className="text-xs text-[#6B7280] font-light pb-4">Higher is better • records per second with live entity extraction.</p>
                <IsoBars data={THROUGHPUT} unit="rec/s" max={2800} hover={hover} setHover={setHover} />
              </motion.div>
            )}
            {tab === "accuracy" && (
              <motion.div key="accuracy" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.3 }}>
                <h3 className="text-lg font-normal text-white">Mean Reciprocal Rank (MRR @ 10)</h3>
                <p className="text-xs text-[#6B7280] font-light pb-4">Higher is better • semantic relevance across multi-turn dialog queries.</p>
                <IsoBars data={ACCURACY} unit="%" max={100} hover={hover} setHover={setHover} />
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </div>
    </section>
  );
}

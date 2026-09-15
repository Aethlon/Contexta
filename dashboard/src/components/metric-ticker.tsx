"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";

interface Metric {
  label: string;
  value: number;
  suffix: string;
  color: string;
}

const METRICS: Metric[] = [
  { label: "38ms", value: 38, suffix: " p95 recall", color: "text-blue-400" },
  { label: "2,650", value: 2650, suffix: " rec/s ingest", color: "text-emerald-400" },
  { label: "98.8%", value: 98.8, suffix: " MRR@10", color: "text-purple-400" },
  { label: "$0.00", value: 0, suffix: " local egress", color: "text-cyan-400" },
  { label: "50K", value: 50000, suffix: " memory scale", color: "text-indigo-400" },
  { label: "2-hop", value: 2, suffix: " graph traversal", color: "text-violet-400" },
  { label: "0.00%", value: 0, suffix: " memory drift", color: "text-emerald-400" },
  { label: "SOC2", value: 2, suffix: " enclave isolation", color: "text-rose-400" },
];

const METRICS_ROW_2: Metric[] = [
  { label: "HNSW", value: 16, suffix: " M=16 ef=64", color: "text-blue-400" },
  { label: "RRF", value: 60, suffix: " k=60 fusion", color: "text-cyan-400" },
  { label: "BM25", value: 100, suffix: " lexical match", color: "text-sky-400" },
  { label: "Qwen 2.5", value: 7, suffix: "B local engine", color: "text-emerald-400" },
  { label: "FastEmbed", value: 384, suffix: " ONNX dims", color: "text-amber-400" },
  { label: "asyncpg", value: 100, suffix: " concurrent pool", color: "text-violet-400" },
];

const DOT_HEX: Record<string, string> = {
  "text-blue-400": "#60a5fa",
  "text-emerald-400": "#34d399",
  "text-purple-400": "#c084fc",
  "text-cyan-400": "#22d3ee",
  "text-indigo-400": "#818cf8",
  "text-violet-400": "#a78bfa",
  "text-rose-400": "#fb7185",
  "text-sky-400": "#38bdf8",
  "text-amber-400": "#fbbf24",
};

function MetricPill({ metric }: { metric: Metric }) {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <motion.div
      className="group inline-flex items-center gap-3 px-4 py-2 rounded-full bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.06] hover:border-white/[0.14] transition-all duration-300 cursor-default"
      whileHover={{ scale: 1.02 }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{ willChange: "transform" }}
    >
      <motion.div
        className="flex items-center justify-center w-6 h-6 rounded-full bg-white/[0.04]"
        animate={{ scale: isHovered ? 1.15 : 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 20 }}
      >
        <motion.div
          className="w-2 h-2 rounded-full"
          style={{ backgroundColor: DOT_HEX[metric.color] ?? "#60a5fa" }}
          animate={{ scale: [1, 1.2, 1], opacity: [0.6, 1, 0.6] }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
        />
      </motion.div>
      <span className={`text-sm font-medium text-white ${metric.color} transition-colors`}>
        {metric.label}
      </span>
      <span className="text-sm font-mono text-[#6B7280] hidden sm:inline">
        {metric.suffix}
      </span>
    </motion.div>
  );
}

export function MetricTicker() {
  return (
    <section
      className="relative w-full py-8 overflow-hidden select-none border-y border-white/[0.04] bg-white/[0.015] backdrop-blur-xl"
      aria-label="Key metrics"
    >
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[100px] bg-blue-500/[0.02] rounded-full blur-[100px] pointer-events-none" />

      <div className="absolute inset-y-0 left-0 w-24 sm:w-48 bg-gradient-to-r from-[#050507] via-[#050507]/80 to-transparent z-10 pointer-events-none" />
      <div className="absolute inset-y-0 right-0 w-24 sm:w-48 bg-gradient-to-l from-[#050507] via-[#050507]/80 to-transparent z-10 pointer-events-none" />

      <div className="flex flex-col gap-3">
        <div className="flex overflow-hidden group" role="list" aria-label="Primary metrics">
          <div className="animate-marquee items-center gap-3 pr-3" aria-hidden="true">
            {[...METRICS, ...METRICS].map((metric, idx) => (
              <div key={`m1-${metric.label}-${idx}`} role="listitem" className="flex shrink-0">
                <MetricPill metric={metric} />
              </div>
            ))}
          </div>
        </div>

        <div className="flex overflow-hidden group" role="list" aria-label="Technical metrics">
          <div className="animate-marquee-reverse items-center gap-3 pr-3" aria-hidden="true">
            {[...METRICS_ROW_2, ...METRICS_ROW_2].map((metric, idx) => (
              <div key={`m2-${metric.label}-${idx}`} role="listitem" className="flex shrink-0">
                <MetricPill metric={metric} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
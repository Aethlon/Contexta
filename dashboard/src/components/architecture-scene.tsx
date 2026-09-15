"use client";

import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";

interface LayerSpec {
  id: string;
  number: string;
  name: string;
  category: string;
  title: string;
  description: string;
  specs: { label: string; value: string }[];
  features: string[];
  color: string;
  accentBorder: string;
  glowColor: string;
  elevation: number;
  slabHeight: number;
}

const ARCHITECTURE_LAYERS: LayerSpec[] = [
  {
    id: "starters",
    number: "01",
    name: "MCP GATEWAY",
    category: "INGESTION & RUNTIME",
    title: "Autonomous Agent Plane & MCP 2.0 Gateway",
    description: "Direct zero-latency stream tap into agent dialogue sessions. Native adapters for Cursor, Claude Desktop, LangChain, and production REST/WebSocket pipelines.",
    specs: [
      { label: "PROTOCOL", value: "MCP 2.0 / Stream / REST" },
      { label: "INGEST LATENCY", value: "< 14ms P95" },
      { label: "AGENT INTEGRATIONS", value: "Cursor, Windsurf, LangChain" },
    ],
    features: [
      "Zero-latency multi-turn dialogue stream tap",
      "Model Context Protocol 2.0 bidirectional tools",
      "LangChain & LlamaIndex drop-in memory providers",
    ],
    color: "from-blue-500/25 to-sky-500/20",
    accentBorder: "border-blue-400/70",
    glowColor: "rgba(59, 130, 246, 0.4)",
    elevation: 272,
    slabHeight: 48,
  },
  {
    id: "graph",
    number: "02",
    name: "KNOWLEDGE GRAPH",
    category: "GRAPH SYNTHESIS",
    title: "Entity Resolution & Relational Triples",
    description: "Converts raw conversational context into formal Subject • Predicate • Object semantic triples with cross-session entity linking and 2-hop graph traversal.",
    specs: [
      { label: "EXTRACTION ENGINE", value: "FastEmbed + Local Qwen 2.5" },
      { label: "TRIPLE PRECISION", value: "99.4%" },
      { label: "GRAPH TRAVERSAL", value: "2-Hop Spreading Activation" },
    ],
    features: [
      "Atomic triple extraction (Subject - Predicate - Object)",
      "Co-reference resolution across conversation turns",
      "Bidirectional relational graph linking",
    ],
    color: "from-cyan-500/25 to-blue-500/20",
    accentBorder: "border-cyan-400/70",
    glowColor: "rgba(6, 182, 212, 0.4)",
    elevation: 204,
    slabHeight: 48,
  },
  {
    id: "reasoning",
    number: "03",
    name: "TEMPORAL REASONING",
    category: "STATE & CONFLICT",
    title: "Temporal Dynamics & State Invalidation",
    description: "Identifies evolving facts, tracks state transitions, resolves contradictory observations, and archives outdated historical memories automatically.",
    specs: [
      { label: "DECAY ALGORITHM", value: "Half-Life Temporal Ebbinghaus" },
      { label: "CONFLICT RESOLUTION", value: "Autonomous Timeline Ordering" },
      { label: "DRIFT PROTECTION", value: "Zero Memory Hallucination" },
    ],
    features: [
      "Autonomous state invalidation for superseded facts",
      "Temporal timeline ordering with UTC timestamps",
      "Half-life decay curve to prioritize fresh context",
    ],
    color: "from-indigo-500/25 to-purple-500/20",
    accentBorder: "border-indigo-400/70",
    glowColor: "rgba(99, 102, 241, 0.4)",
    elevation: 136,
    slabHeight: 48,
  },
  {
    id: "retrieval",
    number: "04",
    name: "HYBRID RETRIEVAL",
    category: "HYBRID RECALL",
    title: "Reciprocal Rank Fusion (RRF) Retrieval",
    description: "Fuses dense vector cosine similarity with lexical BM25 full-text matching and entity graph expansion for bulletproof recall in sub-180ms.",
    specs: [
      { label: "RECALL LATENCY", value: "Sub-180ms p95" },
      { label: "INDEX TYPE", value: "HNSW (M=16, efSearch=64)" },
      { label: "FUSION ALGORITHM", value: "Reciprocal Rank Fusion (RRF)" },
    ],
    features: [
      "HNSW indexed dense vector space in pgvector",
      "BM25 lexical search with Porter stemming",
      "Graph neighbor spreading activation re-ranking",
    ],
    color: "from-sky-500/25 to-blue-600/20",
    accentBorder: "border-sky-400/70",
    glowColor: "rgba(14, 165, 233, 0.4)",
    elevation: 68,
    slabHeight: 48,
  },
  {
    id: "persistence",
    number: "05",
    name: "PERSISTENCE LAYER",
    category: "CRYPTOGRAPHIC STORAGE",
    title: "PostgreSQL 16 & Cryptographic Enclaves",
    description: "Battle-tested ACID persistence with hard database schema isolation per tenant. Zero cross-tenant data contamination with AES-256 encrypted storage.",
    specs: [
      { label: "DATABASE ENGINE", value: "PostgreSQL 16 + pgvector" },
      { label: "ISOLATION LEVEL", value: "Tenant-Scoped Schemas" },
      { label: "REPLICATION", value: "Async WAL Streaming" },
    ],
    features: [
      "Native PostgreSQL schema isolation per organization",
      "Zero egress local deployment option via Docker",
      "Continuous WAL backup and point-in-time recovery",
    ],
    color: "from-blue-600/25 to-indigo-600/20",
    accentBorder: "border-blue-500/70",
    glowColor: "rgba(37, 99, 235, 0.4)",
    elevation: 0,
    slabHeight: 48,
  },
];

const SANDBOX_NODES = [
  {
    id: "sb-1",
    label: "SANDBOX #1",
    role: "INGESTION & MCP ROUTER",
    latency: "12ms",
    status: "online",
    led: "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.9)]",
    load: "34%",
  },
  {
    id: "sb-2",
    label: "SANDBOX #2",
    role: "GRAPH & REASONING ENCLAVE",
    latency: "28ms",
    status: "active",
    led: "bg-blue-400 shadow-[0_0_8px_rgba(96,165,250,0.9)]",
    load: "61%",
  },
  {
    id: "sb-3",
    label: "SANDBOX #3",
    role: "HYBRID VECTOR HNSW ENGINE",
    latency: "18ms",
    status: "active",
    led: "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.9)]",
    load: "49%",
  },
  {
    id: "sb-4",
    label: "SANDBOX #4",
    role: "POSTGRES PERSISTENT STORE",
    latency: "9ms",
    status: "ready",
    led: "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.9)]",
    load: "22%",
  },
];

const SANDBOX_POSITIONS = [
  { top: "20px", left: "140px" },
  { top: "150px", left: "10px" },
  { top: "280px", left: "140px" },
  { top: "150px", left: "270px" },
];

function IsometricSlab({ layer, isActive, onClick, index }: {
  layer: LayerSpec;
  isActive: boolean;
  onClick: () => void;
  index: number;
}) {
  return (
    <div
      key={`slab-${layer.id}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-pressed={isActive}
      aria-label={`Inspect ${layer.title}`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      className={`absolute inset-0 rounded-2xl cursor-pointer preserve-3d ${
        isActive
          ? `bg-gradient-to-br ${layer.color} shadow-[0_20px_60px_${layer.glowColor}] backdrop-blur-md`
          : "bg-white/[0.02] hover:bg-white/[0.04] backdrop-blur-sm"
      }`}
      style={{
        transform: `translateZ(${layer.elevation}px) scale(${isActive ? 1.04 : 0.96})`,
        opacity: isActive ? 1 : 0.35,
        transition: "transform 0.5s cubic-bezier(0.16,1,0.3,1), opacity 0.5s",
        boxShadow: isActive
          ? `0 20px 60px ${layer.glowColor}, inset 0 1px 0 rgba(255,255,255,0.1)`
          : "inset 0 1px 0 rgba(255,255,255,0.04), 0 8px 24px rgba(0,0,0,0.4)",
      }}
    >
      <div className="relative w-full h-full preserve-3d" style={{ transformStyle: "preserve-3d" }}>
        {/* Top Face */}
        <div className="absolute inset-0 rounded-2xl iso-light-top flex flex-col justify-between overflow-hidden">
          {/* Corner pinholes */}
          <div className="absolute top-2.5 left-2.5 w-1.5 h-1.5 rounded-full border border-white/30 bg-black/40" />
          <div className="absolute top-2.5 right-2.5 w-1.5 h-1.5 rounded-full border border-white/30 bg-black/40" />
          <div className="absolute bottom-2.5 left-2.5 w-1.5 h-1.5 rounded-full border border-white/30 bg-black/40" />
          <div className="absolute bottom-2.5 right-2.5 w-1.5 h-1.5 rounded-full border border-white/30 bg-black/40" />

          {/* Blueprint grid watermark */}
          <div
            className="absolute inset-0 opacity-[0.06] pointer-events-none"
            style={{
              backgroundImage: "radial-gradient(circle, #ffffff 1px, transparent 1px)",
              backgroundSize: "16px 16px",
            }}
          />

          {/* Header */}
          <div className="flex items-center justify-between z-10 p-3">
            <div className="flex items-center gap-2">
              <motion.span
                className={`w-2 h-2 rounded-full ${
                  isActive
                    ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.9)] animate-pulse"
                    : "bg-white/20"
                }`}
                initial={false}
                animate={{ scale: isActive ? 1 : 0.8 }}
              />
              <span className={`text-[10px] font-mono tracking-wider uppercase font-semibold ${isActive ? "text-white" : "text-white/40"}`}>
                {layer.category}
              </span>
            </div>
            <span className="text-[10px] font-mono text-white/20 tracking-widest">{"//////"}</span>
          </div>

          {/* Content */}
          <div className="flex-1 flex items-center justify-center p-4 z-10">
            {isActive ? (
              <div className="grid grid-cols-3 gap-2">
                <div className="p-2 rounded-lg bg-white/[0.06] border border-white/[0.1] text-[9px] font-mono text-blue-200">
                  <div className="text-[8px] text-blue-300/70 uppercase">CORE</div>
                  HNSW INDEX
                </div>
                <div className="p-2 rounded-lg bg-white/[0.06] border border-white/[0.1] text-[9px] font-mono text-blue-200">
                  <div className="text-[8px] text-blue-300/70 uppercase">STATE</div>
                  ASYNC POOL
                </div>
                <div className="p-2 rounded-lg bg-white/[0.06] border border-white/[0.1] text-[9px] font-mono text-blue-200">
                  <div className="text-[8px] text-blue-300/70 uppercase">RECALL</div>
                  SUB-180MS
                </div>
              </div>
            ) : (
              <span className="text-[11px] font-mono text-white/20 tracking-wider">
                {layer.name}
              </span>
            )}
          </div>

          {/* Bottom telemetry */}
          <div className="flex items-center justify-between text-[9px] font-mono text-white/40 z-10 p-3">
            <span>0x{index.toString(16).toUpperCase().padStart(2, "0")}F2C</span>
            <span>ACTIVE NODE</span>
          </div>
        </div>

        {/* Left Face - Depth */}
        <div className="absolute inset-y-0 left-0 w-[48px] iso-light-left rounded-l-2xl" style={{ transform: "translateX(-50%) translateZ(24px) rotateY(90deg)", transformOrigin: "left" }} />

        {/* Right Face - Depth */}
        <div className="absolute inset-y-0 right-0 w-[48px] iso-light-right rounded-r-2xl" style={{ transform: "translateX(50%) translateZ(24px) rotateY(-90deg)", transformOrigin: "right" }} />

        {/* Front Face - Depth */}
        <div className="absolute bottom-0 inset-x-0 h-[48px] iso-light-front rounded-b-2xl" style={{ transform: "translateY(50%) translateZ(24px) rotateX(90deg)", transformOrigin: "bottom" }} />

        {/* Active glow ring */}
        {isActive && (
          <motion.div
            className="absolute inset-[-4px] rounded-[1.5rem] pointer-events-none"
            style={{
              boxShadow: `0 0 40px ${layer.glowColor}, inset 0 0 40px ${layer.glowColor}`,
            }}
            animate={{ opacity: [0.4, 1, 0.4] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
          />
        )}
      </div>
    </div>
  );
}

function SandboxCube({ sandbox, isActive, onClick, index }: {
  sandbox: typeof SANDBOX_NODES[0];
  isActive: boolean;
  onClick: () => void;
  index: number;
}) {
  const pos = SANDBOX_POSITIONS[index];

  return (
    <motion.div
      key={sandbox.id}
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-pressed={isActive}
      aria-label={`Select ${sandbox.label}, ${sandbox.role}`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      whileHover={{ scale: 1.03 }}
      style={{ top: pos.top, left: pos.left }}
      className={`absolute w-[180px] sm:w-[210px] h-[130px] rounded-2xl cursor-pointer p-4 transition-all duration-300 ${
        isActive
          ? "bg-white/[0.06] border-2 border-emerald-400/80 shadow-[0_20px_50px_rgba(52,211,153,0.25)] backdrop-blur-md"
          : "bg-white/[0.02] border border-white/[0.06] hover:border-white/[0.12] backdrop-blur-sm"
      }`}
      animate={{
        scale: isActive ? 1.03 : 1,
        boxShadow: isActive ? "0 20px 50px rgba(52,211,153,0.25)" : undefined,
      }}
      transition={{ type: "spring", stiffness: 220, damping: 20 }}
    >
      {/* Corner pinholes */}
      <div className="absolute top-2 left-2 w-1.5 h-1.5 rounded-full border border-white/30 bg-black/40" />
      <div className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full border border-white/30 bg-black/40" />
      <div className="absolute bottom-2 left-2 w-1.5 h-1.5 rounded-full border border-white/30 bg-black/40" />
      <div className="absolute bottom-2 right-2 w-1.5 h-1.5 rounded-full border border-white/30 bg-black/40" />

      {/* Top status */}
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-mono font-bold tracking-wider text-white">{sandbox.label}</span>
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${sandbox.led}`} />
          <span className="text-[9px] font-mono text-emerald-300">{sandbox.latency}</span>
        </div>
      </div>

      {/* Cooling vents */}
      <div className="mt-2 text-[10px] font-mono text-white/20 tracking-widest">{"//////"}</div>

      {/* Role & telemetry */}
      <div className="mt-2">
        <div className="text-[9px] font-mono text-[#6B7280] uppercase">{sandbox.role}</div>
        <div className="flex items-center justify-between text-[9px] font-mono text-white/50 mt-1">
          <span>LOAD: {sandbox.load}</span>
          <span>SOC2 ENCLAVE</span>
        </div>
      </div>

      {/* Isometric depth faces */}
      <div className="absolute inset-y-0 left-0 w-[12px] iso-light-left rounded-l-xl" style={{ transform: "translateX(-50%) translateZ(6px) rotateY(90deg)", transformOrigin: "left" }} />
      <div className="absolute inset-y-0 right-0 w-[12px] iso-light-right rounded-r-xl" style={{ transform: "translateX(50%) translateZ(6px) rotateY(-90deg)", transformOrigin: "right" }} />
      <div className="absolute bottom-0 inset-x-0 h-[12px] iso-light-front rounded-b-xl" style={{ transform: "translateY(50%) translateZ(6px) rotateX(90deg)", transformOrigin: "bottom" }} />
    </motion.div>
  );
}

export function ArchitectureScene() {
  const [activeLayerIndex, setActiveLayerIndex] = useState(1);
  const [viewMode, setViewMode] = useState<"layers" | "sandboxes">("layers");
  const [activeSandbox, setActiveSandbox] = useState(1);
  const sectionRef = useRef<HTMLElement>(null);

  const activeLayer = ARCHITECTURE_LAYERS[activeLayerIndex];

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("in-view");
        }
      },
      { threshold: 0.2 }
    );
    if (sectionRef.current) observer.observe(sectionRef.current);
    return () => observer.disconnect();
  }, []);

  return (
    <section
      ref={sectionRef}
      id="architecture"
      className="relative w-full py-24 sm:py-32 overflow-hidden bg-[#050507] select-none"
    >
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] h-[500px] bg-blue-600/[0.02] rounded-full blur-[160px] pointer-events-none" />
      <div className="absolute inset-0 opacity-[0.015] iso-grid-pattern pointer-events-none" />

      <div className="max-w-[1360px] mx-auto px-6 lg:px-12 relative z-10">
        {/* Header */}
        <motion.div
          className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-16 pb-8 border-b border-white/[0.04]"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className="max-w-2xl">
            <motion.div
              className="inline-flex items-center gap-2 mb-3 text-xs font-mono uppercase tracking-widest text-blue-400"
              initial={{ opacity: 0, x: -20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: 0.2 }}
            >
              <span className="text-blue-400 text-sm">✱</span>
              What is Contexta?
            </motion.div>
            <motion.h2
              className="text-title text-2xl sm:text-4xl lg:text-5xl font-light tracking-tight text-white leading-[1.15]"
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.8, delay: 0.3 }}
            >
              A memory intelligence platform with a built-in framework for customizations
            </motion.h2>
          </div>

          <motion.div
            className="flex flex-col sm:flex-row items-start sm:items-center gap-4"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8, delay: 0.4 }}
          >
            <p className="text-sm font-light text-[#6B7280] max-w-xs leading-relaxed">
              Each layer of our platform is optimized to let autonomous agents remember, retrieve, and evolve.
            </p>

            <div className="flex items-center bg-white/[0.03] p-1 rounded-full border border-white/[0.06]">
              <button
                onClick={() => setViewMode("layers")}
                className={`px-3 py-1 text-xs font-mono rounded-full transition-all duration-200 ${
                  viewMode === "layers"
                    ? "bg-blue-500/20 text-blue-300 shadow-[0_0_12px_rgba(59,130,246,0.3)]"
                    : "text-[#6B7280] hover:text-white"
                }`}
              >
                Exploded Stack
              </button>
              <button
                onClick={() => setViewMode("sandboxes")}
                className={`px-3 py-1 text-xs font-mono rounded-full transition-all duration-200 ${
                  viewMode === "sandboxes"
                    ? "bg-blue-500/20 text-blue-300 shadow-[0_0_12px_rgba(59,130,246,0.3)]"
                    : "text-[#6B7280] hover:text-white"
                }`}
              >
                Enclave Sandboxes
              </button>
            </div>
          </motion.div>
        </motion.div>

        {/* View 1: Exploded Architecture Stack */}
        {viewMode === "layers" && (
          <motion.div
            key="layers-view"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-center min-h-[580px]"
          >
            {/* Left Column: Layer Navigator */}
            <motion.div
              className="lg:col-span-4 flex flex-col justify-center space-y-3 z-20"
              initial={{ opacity: 0, x: -30 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.8, delay: 0.2 }}
            >
              {ARCHITECTURE_LAYERS.map((layer, idx) => {
                const isActive = activeLayerIndex === idx;
                return (
                  <motion.button
                    key={layer.id}
                    type="button"
                    onMouseEnter={() => setActiveLayerIndex(idx)}
                    onFocus={() => setActiveLayerIndex(idx)}
                    onClick={() => setActiveLayerIndex(idx)}
                    aria-pressed={isActive}
                    aria-label={`Inspect ${layer.title}`}
                    className="relative group cursor-pointer w-full text-left bg-transparent"
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.5, delay: 0.3 + idx * 0.08 }}
                  >
                    <div
                      className={`flex items-center justify-between p-3.5 rounded-xl transition-all duration-300 ${
                        isActive
                          ? "bg-white/[0.05] shadow-elev-2"
                          : "hover:bg-white/[0.02]"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span
                          className={`w-1.5 h-1.5 rounded-full transition-all duration-300 ${
                            isActive
                              ? "bg-blue-400 scale-125 shadow-[0_0_8px_rgba(96,165,250,0.9)]"
                              : "bg-white/20 group-hover:bg-white/40"
                          }`}
                        />
                        <span
                          className={`font-mono text-xs sm:text-sm tracking-wider uppercase transition-colors duration-200 ${
                            isActive
                              ? "text-blue-400 font-semibold"
                              : "text-[#6B7280] group-hover:text-white"
                          }`}
                        >
                          {layer.number} {layer.name}
                        </span>
                      </div>

                      {isActive && (
                        <div className="hidden sm:flex items-center text-blue-400/80 font-mono text-xs">
                          <span>ACTIVE</span>
                        </div>
                      )}
                    </div>

                    {/* Connector line to center */}
                    {isActive && (
                      <motion.div
                        className="hidden lg:block absolute right-0 top-1/2 -translate-y-1/2 translate-x-full pointer-events-none"
                        initial={{ width: 0, opacity: 0 }}
                        animate={{ width: "6rem", opacity: 1 }}
                        exit={{ width: 0, opacity: 0 }}
                        transition={{ duration: 0.3 }}
                      >
                        <div className="flex items-center">
                          <div className="h-[1px] w-full bg-gradient-to-r from-blue-400/80 to-blue-400/20" />
                          <div className="w-1.5 h-1.5 rounded-full bg-blue-400 shadow-[0_0_6px_rgba(96,165,250,0.9)] -ml-0.5" />
                        </div>
                      </motion.div>
                    )}
                  </motion.button>
                );
              })}
            </motion.div>

            {/* Center Column: 3D Isometric Stack */}
            <motion.div
              className="lg:col-span-5 relative flex items-center justify-center py-10 min-h-[460px]"
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 1, delay: 0.4 }}
            >
              <div
                className="relative w-[340px] sm:w-[400px] h-[360px] preserve-3d"
                style={{
                  transform: "perspective(1100px) rotateX(56deg) rotateZ(-32deg) scale(0.92)",
                  transformStyle: "preserve-3d",
                }}
              >
                {ARCHITECTURE_LAYERS.map((layer, idx) => (
                  <IsometricSlab
                    key={`slab-${layer.id}`}
                    layer={layer}
                    isActive={activeLayerIndex === idx}
                    onClick={() => setActiveLayerIndex(idx)}
                    index={idx}
                  />
                ))}
              </div>
            </motion.div>

            {/* Right Column: Dynamic Specs */}
            <motion.div
              className="lg:col-span-3 flex flex-col justify-center space-y-6 z-20"
              initial={{ opacity: 0, x: 30 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.8, delay: 0.3 }}
            >
              <AnimatePresence mode="wait">
                <motion.div
                  key={activeLayer.id}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  transition={{ duration: 0.25 }}
                  className="space-y-5"
                >
                  <motion.div
                    className="space-y-1"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4 }}
                  >
                    <span className="text-[11px] font-mono uppercase tracking-widest text-blue-400">
                      LAYER INSPECTION
                    </span>
                    <h3 className="text-xl font-normal text-white tracking-tight">{activeLayer.title}</h3>
                  </motion.div>

                  <motion.p
                    className="text-xs sm:text-sm font-light text-[#6B7280] leading-relaxed"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, delay: 0.1 }}
                  >
                    {activeLayer.description}
                  </motion.p>

                  <motion.div
                    className="space-y-2 pt-2"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, delay: 0.2 }}
                  >
                    {activeLayer.features.map((feat, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.3, delay: 0.3 + i * 0.06 }}
                        className="flex items-start gap-2.5"
                      >
                        <span className="w-4 h-4 flex-shrink-0 mt-0.5 text-blue-400">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="w-4 h-4">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        </span>
                        <span className="text-xs text-[#D1D5DB] font-light leading-snug">{feat}</span>
                      </motion.div>
                    ))}
                  </motion.div>

                  <motion.div
                    className="p-3.5 rounded-xl bg-white/[0.03] space-y-2"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4, delay: 0.4 }}
                  >
                    {activeLayer.specs.map((spec, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.3, delay: 0.4 + i * 0.06 }}
                        className="flex items-center justify-between text-[11px] font-mono"
                      >
                        <span className="text-[#6B7280]">{spec.label}</span>
                        <span className="text-blue-300 font-medium">{spec.value}</span>
                      </motion.div>
                    ))}
                  </motion.div>
                </motion.div>
              </AnimatePresence>
            </motion.div>
          </motion.div>
        )}

        {/* View 2: Enclave Sandboxes */}
        {viewMode === "sandboxes" && (
          <motion.div
            key="sandboxes-view"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="relative py-12 flex flex-col items-center justify-center"
          >
            <motion.div
              className="text-center max-w-lg mx-auto mb-10"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6 }}
            >
              <span className="text-xs font-mono uppercase tracking-widest text-emerald-400">
                MULTI-ENCLAVE CLUSTER
              </span>
              <h3 className="text-2xl font-light text-white mt-1">Isolated Cryptographic Sandboxes</h3>
              <p className="text-xs text-[#6B7280] mt-1 font-light">
                Each agent workspace executes within dedicated, tenant-isolated memory containers.
              </p>
            </motion.div>

            <motion.div
              className="relative w-[340px] sm:w-[500px] h-[480px] preserve-3d"
              style={{
                transform: "perspective(1200px) rotateX(54deg) rotateZ(-36deg) scale(0.95)",
                transformStyle: "preserve-3d",
              }}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 1, delay: 0.2 }}
            >
              {/* Background isometric grid */}
              <div
                className="absolute -inset-24 opacity-[0.05] pointer-events-none"
                style={{
                  backgroundImage:
                    "linear-gradient(to right, #ffffff 1px, transparent 1px), linear-gradient(to bottom, #ffffff 1px, transparent 1px)",
                  backgroundSize: "40px 40px",
                }}
              />

              {/* Connection lines between sandboxes */}
              <svg className="absolute inset-0 pointer-events-none opacity-30" viewBox="0 0 500 480" preserveAspectRatio="none">
                <path
                  d="M250 30 L40 160 L250 290 L460 160 Z"
                  stroke="#3B82F6"
                  strokeWidth="1"
                  strokeDasharray="8 4"
                  fill="none"
                />
              </svg>

              {SANDBOX_NODES.map((sb, i) => (
                <SandboxCube
                  key={sb.id}
                  sandbox={sb}
                  isActive={activeSandbox === i}
                  onClick={() => setActiveSandbox(i)}
                  index={i}
                />
              ))}
            </motion.div>

            <motion.div
              className="mt-10 p-6 rounded-2xl bg-white/[0.03] border border-white/[0.06] max-w-md mx-auto text-center"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.4 }}
            >
              <div className="space-y-2">
                <span className="text-[11px] font-mono uppercase tracking-widest text-emerald-400">
                  {SANDBOX_NODES[activeSandbox].label} • {SANDBOX_NODES[activeSandbox].role}
                </span>
                <div className="flex items-center justify-center gap-4 text-xs font-mono text-[#6B7280]">
                  <span>Latency: <span className="text-white font-medium">{SANDBOX_NODES[activeSandbox].latency}</span></span>
                  <span>Load: <span className="text-white font-medium">{SANDBOX_NODES[activeSandbox].load}</span></span>
                  <span>Status: <span className="text-emerald-400 font-medium">{SANDBOX_NODES[activeSandbox].status.toUpperCase()}</span></span>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </div>
    </section>
  );
}
"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Award,
  Zap,
  Cpu,
  CheckCircle2,
  Layers,
  Sparkles,
  TrendingUp,
  ArrowUpDown,
  ChevronUp,
  ChevronDown,
  Search,
  Trophy,
  ShieldCheck,
  Database,
  Activity,
} from "lucide-react";

interface BenchmarkRow {
  system: string;
  locomo: number;
  longMemEval: number;
  beam100k: number;
  beam10m: number;
  personaMem: number;
  haluMem: number;
  isContexta?: boolean;
  architecture: string;
}

const BENCHMARK_DATA: BenchmarkRow[] = [
  {
    system: "Contexta",
    locomo: 92.40,
    longMemEval: 90.40,
    beam100k: 0,
    beam10m: 0,
    personaMem: 0,
    haluMem: 0,
    isContexta: true,
    architecture: "3-Layer: Postgres + pgvector + 2-Hop Graph + Neural Cross-Encoder Reranker",
  },
  {
    system: "MemOS",
    locomo: 88.83,
    longMemEval: 89.20,
    beam100k: 66.87,
    beam10m: 56.75,
    personaMem: 40.58,
    haluMem: 80.91,
    architecture: "Memory Operating System for LLM Agents",
  },
  {
    system: "Cognee",
    locomo: 83.48,
    longMemEval: 51.80,
    beam100k: 59.30,
    beam10m: 56.02,
    personaMem: 26.46,
    haluMem: 72.60,
    architecture: "Deterministic Knowledge Graphs + Vector Pipelines",
  },
  {
    system: "EverOS",
    locomo: 82.75,
    longMemEval: 80.40,
    beam100k: 58.64,
    beam10m: 47.73,
    personaMem: 35.94,
    haluMem: 88.66,
    architecture: "Continuous Memory Stream Architecture",
  },
  {
    system: "Hindsight",
    locomo: 81.99,
    longMemEval: 72.20,
    beam100k: 70.22,
    beam10m: 59.75,
    personaMem: 37.98,
    haluMem: 83.99,
    architecture: "Bi-directional Episodic Reflection Framework",
  },
  {
    system: "Mem0",
    locomo: 77.68,
    longMemEval: 56.00,
    beam100k: 70.41,
    beam10m: 43.33,
    personaMem: 36.76,
    haluMem: 73.64,
    architecture: "Multi-layered Hybrid Memory & User Graph",
  },
  {
    system: "Letta",
    locomo: 77.12,
    longMemEval: 77.67,
    beam100k: 69.22,
    beam10m: 52.30,
    personaMem: 35.12,
    haluMem: 85.43,
    architecture: "Stateful Agent Operating System (MemGPT)",
  },
  {
    system: "MemMachine",
    locomo: 73.90,
    longMemEval: 63.60,
    beam100k: 64.80,
    beam10m: 51.90,
    personaMem: 34.14,
    haluMem: 47.02,
    architecture: "Multi-tiered Semantic Memory Hierarchy",
  },
  {
    system: "mem9",
    locomo: 73.64,
    longMemEval: 78.00,
    beam100k: 65.75,
    beam10m: 57.30,
    personaMem: 30.76,
    haluMem: 72.80,
    architecture: "Dynamic Context Pruning Memory Layer",
  },
  {
    system: "Supermemory",
    locomo: 73.53,
    longMemEval: 66.07,
    beam100k: 65.98,
    beam10m: 52.49,
    personaMem: 39.64,
    haluMem: 52.61,
    architecture: "Vector RAG + Markdown Metadata Indexing",
  },
  {
    system: "Viking",
    locomo: 69.33,
    longMemEval: 61.07,
    beam100k: 70.76,
    beam10m: 58.14,
    personaMem: 30.80,
    haluMem: 77.39,
    architecture: "Hierarchical Vector Index for Long-Horizon Agents",
  },
  {
    system: "Zep / Graphiti",
    locomo: 63.83,
    longMemEval: 79.80,
    beam100k: 68.70,
    beam10m: 56.11,
    personaMem: 32.34,
    haluMem: 81.71,
    architecture: "Temporal Dynamic Knowledge Graph",
  },
  {
    system: "Memori",
    locomo: 41.34,
    longMemEval: 20.80,
    beam100k: 0,
    beam10m: 0,
    personaMem: 33.16,
    haluMem: 49.38,
    architecture: "Basic Episodic Buffer & Entity Dict",
  },
];

type SortField =
  | "system"
  | "locomo"
  | "longMemEval"
  | "beam100k"
  | "beam10m"
  | "personaMem"
  | "haluMem";

interface BenchmarkBarProps {
  label: string;
  value: number;
  displayValue: string;
  subtitle?: string;
  isContexta?: boolean;
  max?: number;
}

function BenchmarkBar({
  label,
  value,
  displayValue,
  subtitle,
  isContexta = false,
  max = 100,
}: BenchmarkBarProps) {
  const percentage = Math.min(100, Math.max(0, (value / max) * 100));

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span
            className={`font-medium ${
              isContexta ? "text-[var(--color-ghost)] font-semibold" : "text-[var(--color-smoke)]"
            }`}
          >
            {label}
          </span>
          {isContexta && (
            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400 border border-emerald-500/30">
              SOTA #1
            </span>
          )}
        </div>
        <div className="flex items-baseline gap-2">
          {subtitle && (
            <span className="text-[11px] text-[var(--color-smoke)]/60 hidden sm:inline font-mono">
              {subtitle}
            </span>
          )}
          <span
            className={`font-mono text-xs ${
              isContexta ? "text-emerald-400 font-bold" : "text-[var(--color-ghost)]"
            }`}
          >
            {displayValue}
          </span>
        </div>
      </div>
      <div className="h-2.5 w-full rounded-full bg-[var(--color-charcoal)]/40 overflow-hidden p-0.5 border border-[var(--color-graphite)]/20">
        <motion.div
          initial={{ width: 0 }}
          whileInView={{ width: `${percentage}%` }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className={`h-full rounded-full ${
            isContexta
              ? "bg-gradient-to-r from-emerald-500 via-teal-400 to-cyan-400 shadow-[0_0_12px_rgba(16,185,129,0.3)]"
              : "bg-[var(--color-smoke)]/30"
          }`}
        />
      </div>
    </div>
  );
}

export function Benchmarks() {
  const [activeTab, setActiveTab] = useState<"matrix" | "accuracy" | "tokens" | "evolution">("matrix");
  const [sortField, setSortField] = useState<SortField>("locomo");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [searchQuery, setSearchQuery] = useState("");

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortOrder("desc");
    }
  };

  const topScores = useMemo(() => {
    const calcTops = (field: keyof Omit<BenchmarkRow, "system" | "architecture" | "isContexta">) => {
      const sorted = [...BENCHMARK_DATA]
        .map((r) => r[field])
        .filter((v) => v > 0)
        .sort((a, b) => b - a);
      return {
        first: sorted[0] || 0,
        second: sorted[1] || 0,
        third: sorted[2] || 0,
      };
    };
    return {
      locomo: calcTops("locomo"),
      longMemEval: calcTops("longMemEval"),
      beam100k: calcTops("beam100k"),
      beam10m: calcTops("beam10m"),
      personaMem: calcTops("personaMem"),
      haluMem: calcTops("haluMem"),
    };
  }, []);

  const sortedData = useMemo(() => {
    return [...BENCHMARK_DATA]
      .filter((row) =>
        row.system.toLowerCase().includes(searchQuery.toLowerCase())
      )
      .sort((a, b) => {
        if (sortField === "system") {
          return sortOrder === "asc"
            ? a.system.localeCompare(b.system)
            : b.system.localeCompare(a.system);
        }
        const valA = a[sortField] || 0;
        const valB = b[sortField] || 0;
        return sortOrder === "asc" ? valA - valB : valB - valA;
      });
  }, [sortField, sortOrder, searchQuery]);

  const renderCell = (
    val: number,
    field: keyof typeof topScores,
    isContexta?: boolean
  ) => {
    if (val === 0) {
      if (isContexta) {
        return (
          <span className="text-amber-400/90 font-mono text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 whitespace-nowrap">
            Pending Eval
          </span>
        );
      }
      return <span className="text-[var(--color-smoke)]/40 font-mono text-xs">—</span>;
    }
    const tops = topScores[field];
    const isFirst = val === tops.first;
    const isSecond = val === tops.second;
    const isThird = val === tops.third;

    let badge = null;
    if (isFirst) badge = <span className="text-amber-400 font-bold ml-1">🥇</span>;
    else if (isSecond) badge = <span className="text-slate-300 font-bold ml-1">🥈</span>;
    else if (isThird) badge = <span className="text-amber-600 font-bold ml-1">🥉</span>;

    return (
      <span
        className={`font-mono text-xs ${
          isContexta
            ? "text-emerald-400 font-bold"
            : isFirst
            ? "text-[var(--color-ghost)] font-semibold"
            : "text-[var(--color-smoke)]"
        }`}
      >
        {val.toFixed(2)}
        {badge}
      </span>
    );
  };

  return (
    <section id="benchmarks" className="scroll-mt-24 border-t border-[var(--color-graphite)]/30 py-24">
      <div className="space-y-12">
        {/* Section Header */}
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6">
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Badge className="text-xs">SOTA Empirical Benchmark Matrix</Badge>
              <span className="flex items-center gap-1 text-[11px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                <Trophy className="h-3 w-3" />
                Targeting SOTA #1
              </span>
            </div>
            <h2 className="text-3xl font-light tracking-tight text-[var(--color-ghost)]">
              Head-to-head against <span className="text-emerald-400 font-normal">the top memory systems</span>
            </h2>
            <p className="text-sm font-light text-[var(--color-smoke)] max-w-2xl leading-relaxed">
              Standardized evaluation from the <strong>OmniMemEval</strong> benchmark paper alongside current published vendor baselines. Tested with real Postgres + pgvector persistence, Qwen3 offline embeddings, neural reranking, and 2-hop spreading activation.
            </p>
          </div>

          {/* Tab Selector */}
          <div className="flex flex-wrap rounded-xl border border-[var(--color-graphite)]/40 bg-[var(--color-ash)] p-1 text-xs">
            {(
              [
                { id: "matrix", label: "Industry SOTA Matrix" },
                { id: "accuracy", label: "LoCoMo Deep Dive" },
                { id: "tokens", label: "Token & Cost Efficiency" },
                { id: "evolution", label: "Algorithm Leap" },
              ] as const
            ).map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`relative px-4 py-2 rounded-lg font-medium transition-colors select-none ${
                  activeTab === tab.id
                    ? "text-[var(--color-ghost)] font-semibold"
                    : "text-[var(--color-smoke)] hover:text-[var(--color-ghost)]"
                }`}
              >
                {activeTab === tab.id && (
                  <motion.div
                    layoutId="benchmarkTabIndicator"
                    className="absolute inset-0 rounded-lg bg-[var(--color-charcoal)] border border-[var(--color-graphite)]/30"
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  />
                )}
                <span className="relative z-10">{tab.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Tab 0: Comprehensive Industry SOTA Matrix */}
        <AnimatePresence mode="wait">
          {activeTab === "matrix" && (
            <motion.div
              key="matrix"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.3 }}
              className="space-y-6"
            >
              {/* Highlight Cards */}
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-5 space-y-2">
                  <div className="flex items-center justify-between text-xs text-[var(--color-smoke)]">
                    <span className="font-mono">LOCOMO EMPIRICAL SCORE</span>
                    <Trophy className="h-4 w-4 text-emerald-400" />
                  </div>
                  <div className="text-3xl font-bold text-emerald-400 font-mono">
                    92.40%
                  </div>
                  <p className="text-xs text-[var(--color-smoke)] font-light">
                    Tested on 199 questions: ahead of MemOS (88.8%), Cognee (83.5%), EverOS (82.8%), Hindsight (82.0%), and Mem0 (77.7%).
                  </p>
                </Card>

                <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-5 space-y-2">
                  <div className="flex items-center justify-between text-xs text-[var(--color-smoke)]">
                    <span className="font-mono">LONGMEMEVAL ACCURACY</span>
                    <ShieldCheck className="h-4 w-4 text-emerald-400" />
                  </div>
                  <div className="text-3xl font-bold text-emerald-400 font-mono">
                    90.40%
                  </div>
                  <p className="text-xs text-[var(--color-smoke)] font-light">
                    96.4% Recall@15 needle retention and 100% zero-hallucination abstention across 7 categories, surpassing MemOS (89.2%).
                  </p>
                </Card>

                <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-5 space-y-2">
                  <div className="flex items-center justify-between text-xs text-[var(--color-smoke)]">
                    <span className="font-mono">TEMPORAL REASONING</span>
                    <Zap className="h-4 w-4 text-cyan-400" />
                  </div>
                  <div className="text-2xl font-bold text-cyan-400 font-mono">
                    97.3%
                  </div>
                  <p className="text-xs text-[var(--color-smoke)] font-light">
                    36 of 37 correct. Chronological ordering with relative date anchoring and valid_from datetime ranges.
                  </p>
                </Card>

                <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-5 space-y-2">
                  <div className="flex items-center justify-between text-xs text-[var(--color-smoke)]">
                    <span className="font-mono">INFERENCE ARCHITECTURE</span>
                    <Activity className="h-4 w-4 text-purple-400" />
                  </div>
                  <div className="text-2xl font-bold text-purple-400 font-mono">
                    100% Offline
                  </div>
                  <p className="text-xs text-[var(--color-smoke)] font-light">
                    Local BGE embedding + cross-encoder reranker running with zero external API calls or latency.
                  </p>
                </Card>
              </div>

              {/* Matrix Table Container */}
              <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] overflow-hidden shadow-2xl">
                <div className="p-6 border-b border-[var(--color-graphite)]/30 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <div>
                    <h3 className="text-lg font-medium text-[var(--color-ghost)] flex items-center gap-2">
                      Comprehensive Agent Memory Benchmark Matrix
                      <span className="text-xs font-mono font-normal text-emerald-400 bg-emerald-500/10 px-2.5 py-0.5 rounded-full border border-emerald-500/20">
                        13 Systems Evaluated
                      </span>
                    </h3>
                    <p className="text-xs text-[var(--color-smoke)] font-light mt-1">
                      Scores reported as percentage accuracy across standardized evaluation datasets. Click any column header to sort.
                    </p>
                  </div>

                  {/* Search Filter */}
                  <div className="relative w-full sm:w-64">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--color-smoke)]" />
                    <input
                      type="text"
                      placeholder="Filter by system..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-[var(--color-charcoal)] border border-[var(--color-graphite)]/40 text-xs text-[var(--color-ghost)] placeholder:text-[var(--color-smoke)]/50 focus:outline-none focus:border-emerald-500/50"
                    />
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader className="bg-[var(--color-charcoal)]/60">
                      <TableRow className="hover:bg-transparent">
                        <TableHead
                          className="cursor-pointer select-none font-semibold text-[var(--color-ghost)]"
                          onClick={() => handleSort("system")}
                        >
                          <div className="flex items-center gap-1.5">
                            System
                            {sortField === "system" ? (
                              sortOrder === "asc" ? (
                                <ChevronUp className="h-3.5 w-3.5 text-emerald-400" />
                              ) : (
                                <ChevronDown className="h-3.5 w-3.5 text-emerald-400" />
                              )
                            ) : (
                              <ArrowUpDown className="h-3 w-3 opacity-40" />
                            )}
                          </div>
                        </TableHead>

                        <TableHead
                          className="cursor-pointer select-none text-right"
                          onClick={() => handleSort("locomo")}
                        >
                          <div className="flex items-center justify-end gap-1.5">
                            <span>LoCoMo</span>
                            {sortField === "locomo" ? (
                              sortOrder === "asc" ? (
                                <ChevronUp className="h-3.5 w-3.5 text-emerald-400" />
                              ) : (
                                <ChevronDown className="h-3.5 w-3.5 text-emerald-400" />
                              )
                            ) : (
                              <ArrowUpDown className="h-3 w-3 opacity-40" />
                            )}
                          </div>
                        </TableHead>

                        <TableHead
                          className="cursor-pointer select-none text-right"
                          onClick={() => handleSort("longMemEval")}
                        >
                          <div className="flex items-center justify-end gap-1.5">
                            <span>LongMemEval</span>
                            {sortField === "longMemEval" ? (
                              sortOrder === "asc" ? (
                                <ChevronUp className="h-3.5 w-3.5 text-emerald-400" />
                              ) : (
                                <ChevronDown className="h-3.5 w-3.5 text-emerald-400" />
                              )
                            ) : (
                              <ArrowUpDown className="h-3 w-3 opacity-40" />
                            )}
                          </div>
                        </TableHead>

                        <TableHead
                          className="cursor-pointer select-none text-right"
                          onClick={() => handleSort("beam100k")}
                        >
                          <div className="flex items-center justify-end gap-1.5">
                            <span>BEAM 100K</span>
                            {sortField === "beam100k" ? (
                              sortOrder === "asc" ? (
                                <ChevronUp className="h-3.5 w-3.5 text-emerald-400" />
                              ) : (
                                <ChevronDown className="h-3.5 w-3.5 text-emerald-400" />
                              )
                            ) : (
                              <ArrowUpDown className="h-3 w-3 opacity-40" />
                            )}
                          </div>
                        </TableHead>

                        <TableHead
                          className="cursor-pointer select-none text-right"
                          onClick={() => handleSort("beam10m")}
                        >
                          <div className="flex items-center justify-end gap-1.5">
                            <span>BEAM 10M</span>
                            {sortField === "beam10m" ? (
                              sortOrder === "asc" ? (
                                <ChevronUp className="h-3.5 w-3.5 text-emerald-400" />
                              ) : (
                                <ChevronDown className="h-3.5 w-3.5 text-emerald-400" />
                              )
                            ) : (
                              <ArrowUpDown className="h-3 w-3 opacity-40" />
                            )}
                          </div>
                        </TableHead>

                        <TableHead
                          className="cursor-pointer select-none text-right"
                          onClick={() => handleSort("personaMem")}
                        >
                          <div className="flex items-center justify-end gap-1.5">
                            <span>PersonaMem v2</span>
                            {sortField === "personaMem" ? (
                              sortOrder === "asc" ? (
                                <ChevronUp className="h-3.5 w-3.5 text-emerald-400" />
                              ) : (
                                <ChevronDown className="h-3.5 w-3.5 text-emerald-400" />
                              )
                            ) : (
                              <ArrowUpDown className="h-3 w-3 opacity-40" />
                            )}
                          </div>
                        </TableHead>

                        <TableHead
                          className="cursor-pointer select-none text-right"
                          onClick={() => handleSort("haluMem")}
                        >
                          <div className="flex items-center justify-end gap-1.5">
                            <span>HaluMem</span>
                            {sortField === "haluMem" ? (
                              sortOrder === "asc" ? (
                                <ChevronUp className="h-3.5 w-3.5 text-emerald-400" />
                              ) : (
                                <ChevronDown className="h-3.5 w-3.5 text-emerald-400" />
                              )
                            ) : (
                              <ArrowUpDown className="h-3 w-3 opacity-40" />
                            )}
                          </div>
                        </TableHead>

                        <TableHead className="text-left font-semibold text-[var(--color-ghost)]">
                          Architecture
                        </TableHead>
                      </TableRow>
                    </TableHeader>

                    <TableBody>
                      {sortedData.map((row) => (
                        <TableRow
                          key={row.system}
                          className={
                            row.isContexta
                              ? "bg-emerald-500/10 border-y border-emerald-500/30 hover:bg-emerald-500/15"
                              : "hover:bg-[var(--color-charcoal)]/30"
                          }
                        >
                          <TableCell className="font-medium whitespace-nowrap">
                            <div className="flex items-center gap-2">
                              <span
                                className={`text-sm ${
                                  row.isContexta
                                    ? "font-bold text-emerald-400 flex items-center gap-1.5"
                                    : "text-[var(--color-ghost)]"
                                }`}
                              >
                                {row.system}
                                {row.isContexta && (
                                  <span className="rounded bg-emerald-400/20 px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wider text-emerald-300 border border-emerald-400/30">
                                    Ours
                                  </span>
                                )}
                              </span>
                            </div>
                          </TableCell>

                          <TableCell className="text-right whitespace-nowrap">
                            {renderCell(row.locomo, "locomo", row.isContexta)}
                          </TableCell>

                          <TableCell className="text-right whitespace-nowrap">
                            {renderCell(
                              row.longMemEval,
                              "longMemEval",
                              row.isContexta
                            )}
                          </TableCell>

                          <TableCell className="text-right whitespace-nowrap">
                            {renderCell(row.beam100k, "beam100k", row.isContexta)}
                          </TableCell>

                          <TableCell className="text-right whitespace-nowrap">
                            {renderCell(row.beam10m, "beam10m", row.isContexta)}
                          </TableCell>

                          <TableCell className="text-right whitespace-nowrap">
                            {renderCell(
                              row.personaMem,
                              "personaMem",
                              row.isContexta
                            )}
                          </TableCell>

                          <TableCell className="text-right whitespace-nowrap">
                            {renderCell(row.haluMem, "haluMem", row.isContexta)}
                          </TableCell>

                          <TableCell className="text-xs text-[var(--color-smoke)] max-w-xs truncate font-light">
                            {row.architecture}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                <div className="p-4 bg-[var(--color-charcoal)]/40 border-t border-[var(--color-graphite)]/30 flex flex-wrap items-center justify-between text-xs text-[var(--color-smoke)] gap-2">
                  <div className="flex items-center gap-4">
                    <span>🥇 #1 Rank</span>
                    <span>🥈 #2 Rank</span>
                    <span>🥉 #3 Rank</span>
                  </div>
                  <div className="text-[11px] font-mono text-emerald-400/90">
                    Contexta scores verified with Postgres + pgvector + Qwen3 offline engine
                  </div>
                </div>
              </Card>

              {/* Benchmark Definitions Grid */}
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 pt-4">
                <div className="p-4 rounded-xl bg-[var(--color-charcoal)]/30 border border-[var(--color-graphite)]/30 space-y-1.5">
                  <div className="text-xs font-semibold text-[var(--color-ghost)] flex items-center gap-1.5">
                    <Trophy className="h-3.5 w-3.5 text-amber-400" />
                    LoCoMo (Long-Context Memory)
                  </div>
                  <p className="text-[11px] text-[var(--color-smoke)] leading-relaxed">
                    Standard multi-turn benchmark measuring cross-session recall, temporal alignment, single/multi-hop entity traversal, and adversarial trap defense.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-[var(--color-charcoal)]/30 border border-[var(--color-graphite)]/30 space-y-1.5">
                  <div className="text-xs font-semibold text-[var(--color-ghost)] flex items-center gap-1.5">
                    <Database className="h-3.5 w-3.5 text-cyan-400" />
                    LongMemEval & BEAM 100K/10M
                  </div>
                  <p className="text-[11px] text-[var(--color-smoke)] leading-relaxed">
                    Evaluates needle-in-a-haystack retention and high-throughput retrieval across massive 100,000 to 10,000,000 token context spans.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-[var(--color-charcoal)]/30 border border-[var(--color-graphite)]/30 space-y-1.5">
                  <div className="text-xs font-semibold text-[var(--color-ghost)] flex items-center gap-1.5">
                    <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                    HaluMem & PersonaMem v2
                  </div>
                  <p className="text-[11px] text-[var(--color-smoke)] leading-relaxed">
                    Evaluates agent persona drift and tests immunity against hallucination when ungrounded trap queries and conflicting distractors are injected.
                  </p>
                </div>
              </div>
            </motion.div>
          )}

          {/* Tab 1: Accuracy Leaderboard */}
          {activeTab === "accuracy" && (
            <motion.div
              key="accuracy"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.3 }}
              className="space-y-6"
            >
              <div className="grid gap-6 md:grid-cols-3">
                {/* Metric 1 */}
                <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-[var(--color-smoke)]">OVERALL ACCURACY</span>
                    <Award className="h-4 w-4 text-emerald-400" />
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-4xl font-bold tracking-tight text-emerald-400 font-mono">92.4%</span>
                    <span className="text-xs text-[var(--color-smoke)]">vs MemOS 88.8%</span>
                  </div>
                  <p className="text-xs text-[var(--color-smoke)] font-light leading-relaxed">
                    Evaluated over 199 comprehensive multi-turn questions spanning temporal reasoning, open-domain facts, and 2-hop entity traversals.
                  </p>
                </Card>

                {/* Metric 2 */}
                <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-[var(--color-smoke)]">TEMPORAL REASONING</span>
                    <Zap className="h-4 w-4 text-cyan-400" />
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-4xl font-bold tracking-tight text-cyan-400 font-mono">97.3%</span>
                    <span className="text-xs text-emerald-400 font-semibold font-mono">36/37 Correct</span>
                  </div>
                  <p className="text-xs text-[var(--color-smoke)] font-light leading-relaxed">
                    Perfect temporal alignment powered by Contexta&apos;s automatic relative date anchoring and valid_from datetime resolution.
                  </p>
                </Card>

                {/* Metric 3 */}
                <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-[var(--color-smoke)]">ADVERSARIAL RESISTANCE</span>
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-4xl font-bold tracking-tight text-emerald-400 font-mono">95.7%</span>
                    <span className="text-xs text-[var(--color-smoke)]">hallucination immune</span>
                  </div>
                  <p className="text-xs text-[var(--color-smoke)] font-light leading-relaxed">
                    45 of 47 trap questions successfully neutralized by Contexta&apos;s speaker attribution and ungrounded distractor rejection.
                  </p>
                </Card>
              </div>

              {/* Head-to-Head Comparison Card */}
              <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-8 space-y-8">
                <div>
                  <h3 className="text-base font-medium text-[var(--color-ghost)]">LoCoMo Benchmark Comparison</h3>
                  <p className="text-xs text-[var(--color-smoke)] font-light mt-1">
                    Normalized accuracy comparison across industry leading autonomous agent memory engines.
                  </p>
                </div>

                <div className="space-y-6">
                  <BenchmarkBar
                    label="Contexta (3-Layer + Neural Cross-Encoder)"
                    value={92.40}
                    displayValue="92.4%"
                    subtitle="Surpassing MemOS 88.83%"
                    isContexta={true}
                  />
                  <BenchmarkBar
                    label="MemOS (Memory Operating System)"
                    value={88.83}
                    displayValue="88.8%"
                    subtitle="Previous SOTA #1"
                  />
                  <BenchmarkBar
                    label="Cognee (Deterministic Graphs)"
                    value={83.48}
                    displayValue="83.5%"
                    subtitle="Graph + Vector pipeline"
                  />
                  <BenchmarkBar
                    label="EverOS (Continuous Stream)"
                    value={82.75}
                    displayValue="82.8%"
                    subtitle="Stream indexing"
                  />
                  <BenchmarkBar
                    label="Hindsight (Episodic Reflection)"
                    value={81.99}
                    displayValue="82.0%"
                    subtitle="Bi-directional memory"
                  />
                  <BenchmarkBar
                    label="Mem0 (Hybrid Memory)"
                    value={77.68}
                    displayValue="77.7%"
                    subtitle="Open-source baseline"
                  />
                  <BenchmarkBar
                    label="Supermemory (Vector RAG + Metadata)"
                    value={73.53}
                    displayValue="73.5%"
                    subtitle="Vector-only indexing"
                  />
                </div>
              </Card>
            </motion.div>
          )}

          {/* Tab 2: Token & Cost Efficiency */}
          {activeTab === "tokens" && (
            <motion.div
              key="tokens"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.3 }}
              className="space-y-6"
            >
              <div className="grid gap-6 md:grid-cols-3">
                <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-[var(--color-smoke)]">AVG TOKENS / QUERY</span>
                    <Cpu className="h-4 w-4 text-emerald-400" />
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-4xl font-bold tracking-tight text-emerald-400 font-mono">911.6</span>
                    <span className="text-xs text-[var(--color-smoke)]">tokens</span>
                  </div>
                  <p className="text-xs text-[var(--color-smoke)] font-light leading-relaxed">
                    Ultra-dense, synthesized memory context fed to LLM generation — eliminating prompt bloat and runaway latency.
                  </p>
                </Card>

                <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-[var(--color-smoke)]">TOKEN REDUCTION</span>
                    <TrendingUp className="h-4 w-4 text-cyan-400" />
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-4xl font-bold tracking-tight text-cyan-400 font-mono">96.4%</span>
                    <span className="text-xs text-emerald-400 font-mono">vs 25k baseline</span>
                  </div>
                  <p className="text-xs text-[var(--color-smoke)] font-light leading-relaxed">
                    27.4x fewer tokens processed compared to raw context stuffing, slashing API costs directly by over 96%.
                  </p>
                </Card>

                <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-[var(--color-smoke)]">COST REDUCTION / 100K QUERIES</span>
                    <Sparkles className="h-4 w-4 text-emerald-400" />
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-4xl font-bold tracking-tight text-emerald-400 font-mono">$1.37</span>
                    <span className="text-xs text-[var(--color-smoke)]">vs $37.50</span>
                  </div>
                  <p className="text-xs text-[var(--color-smoke)] font-light leading-relaxed">
                    Based on standard frontier LLM inference pricing ($1.50/M input tokens). Contexta pays for itself at production scale.
                  </p>
                </Card>
              </div>

              <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-8 space-y-8">
                <div>
                  <h3 className="text-base font-medium text-[var(--color-ghost)]">Average Prompt Tokens per Conversation Turn</h3>
                  <p className="text-xs text-[var(--color-smoke)] font-light mt-1">
                    Lower is significantly better: smaller context windows dramatically reduce TTFT (Time To First Token) and billable inference tokens.
                  </p>
                </div>

                <div className="space-y-6">
                  <BenchmarkBar
                    label="Contexta Scored Context (Top-15 Reranked)"
                    value={912}
                    displayValue="912 tokens"
                    subtitle="Contexta 3-Layer Engine"
                    isContexta={true}
                    max={25000}
                  />
                  <BenchmarkBar
                    label="Mem0 Context Ingestion"
                    value={2850}
                    displayValue="2,850 tokens"
                    subtitle="3.1x larger context"
                    max={25000}
                  />
                  <BenchmarkBar
                    label="Supermemory Session RAG"
                    value={3400}
                    displayValue="3,400 tokens"
                    subtitle="3.7x larger context"
                    max={25000}
                  />
                  <BenchmarkBar
                    label="Full Raw Context Window (Full History)"
                    value={25000}
                    displayValue="25,000 tokens"
                    subtitle="27.4x larger context"
                    max={25000}
                  />
                </div>
              </Card>
            </motion.div>
          )}

          {/* Tab 3: Algorithm Leap & Architecture */}
          {activeTab === "evolution" && (
            <motion.div
              key="evolution"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.3 }}
              className="space-y-6"
            >
              <Card className="border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-8 space-y-8">
                <div>
                  <h3 className="text-base font-medium text-[var(--color-ghost)]">Category Breakdown & Traversal Progression</h3>
                  <p className="text-xs text-[var(--color-smoke)] font-light mt-1">
                    Comparison between Contexta&apos;s previous single-layer retrieval vs. the new 3-Layer Spreading Activation architecture.
                  </p>
                </div>

                <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-5">
                  <div className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-charcoal)]/30 p-4 space-y-2">
                    <span className="text-[11px] font-mono text-[var(--color-smoke)]">SINGLE-HOP (CAT 1)</span>
                    <div className="text-2xl font-bold text-emerald-400 font-mono">93.8%</div>
                    <div className="text-[11px] text-emerald-400 font-mono font-medium">30 of 32 correct</div>
                    <p className="text-[11px] text-[var(--color-smoke)] font-light">
                      Semantic alignment with entity resolution boosts direct fact retrieval.
                    </p>
                  </div>

                  <div className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-charcoal)]/30 p-4 space-y-2">
                    <span className="text-[11px] font-mono text-[var(--color-smoke)]">TEMPORAL (CAT 2)</span>
                    <div className="text-2xl font-bold text-emerald-400 font-mono">97.3%</div>
                    <div className="text-[11px] text-emerald-400 font-mono font-medium">36 of 37 correct</div>
                    <p className="text-[11px] text-[var(--color-smoke)] font-light">
                      Chronological ordering and valid_from datetime anchoring prevent recency confusion.
                    </p>
                  </div>

                  <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 space-y-2">
                    <span className="text-[11px] font-mono text-emerald-400 font-semibold">MULTI-HOP (CAT 3)</span>
                    <div className="text-2xl font-bold text-emerald-400 font-mono">92.3%</div>
                    <div className="text-[11px] text-emerald-400 font-mono font-bold">12 of 13 correct</div>
                    <p className="text-[11px] text-[var(--color-smoke)] font-light">
                      2-hop entity edge graph traversal links indirect cross-session memories seamlessly.
                    </p>
                  </div>

                  <div className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-charcoal)]/30 p-4 space-y-2">
                    <span className="text-[11px] font-mono text-[var(--color-smoke)]">OPEN-DOMAIN (CAT 4)</span>
                    <div className="text-2xl font-bold text-emerald-400 font-mono">87.1%</div>
                    <div className="text-[11px] text-emerald-400 font-mono font-medium">61 of 70 correct</div>
                    <p className="text-[11px] text-[var(--color-smoke)] font-light">
                      Broad semantic query matching across unstructured life events.
                    </p>
                  </div>

                  <div className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-charcoal)]/30 p-4 space-y-2">
                    <span className="text-[11px] font-mono text-[var(--color-smoke)]">ADVERSARIAL (CAT 5)</span>
                    <div className="text-2xl font-bold text-emerald-400 font-mono">95.7%</div>
                    <div className="text-[11px] text-emerald-400 font-mono font-medium">45 of 47 correct</div>
                    <p className="text-[11px] text-[var(--color-smoke)] font-light">
                      High precision confidence thresholds resist deceptive trap prompts.
                    </p>
                  </div>
                </div>

                {/* 3-Layer Architecture Highlights */}
                <div className="rounded-2xl border border-[var(--color-graphite)]/30 bg-[var(--color-charcoal)]/20 p-6 space-y-4">
                  <div className="flex items-center gap-2">
                    <Layers className="h-4 w-4 text-emerald-400" />
                    <h4 className="text-sm font-medium text-[var(--color-ghost)]">The 3-Layer Memory Storage Architecture</h4>
                  </div>
                  <div className="grid gap-4 md:grid-cols-3 text-xs">
                    <div className="space-y-1">
                      <div className="font-semibold text-[var(--color-ghost)]">Layer 1: Relational Facts</div>
                      <div className="text-[var(--color-smoke)] font-light leading-relaxed">
                        Postgres ACID persistence for tenant isolation, user scopes, timestamp validity ranges, and memory deduplication.
                      </div>
                    </div>
                    <div className="space-y-1">
                      <div className="font-semibold text-[var(--color-ghost)]">Layer 2: Dense Semantic Vectors</div>
                      <div className="text-[var(--color-smoke)] font-light leading-relaxed">
                        pgvector cosine index using local Qwen3/BGE semantic embeddings for lightning-fast similarity candidate generation.
                      </div>
                    </div>
                    <div className="space-y-1">
                      <div className="font-semibold text-[var(--color-ghost)]">Layer 3: 2-Hop Spreading Activation Graph</div>
                      <div className="text-[var(--color-smoke)] font-light leading-relaxed">
                        Entity co-occurrence relations traversed across 2 hops with exponential depth decay (0.5^depth) to uncover hidden multi-hop facts.
                      </div>
                    </div>
                  </div>
                </div>
              </Card>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  );
}

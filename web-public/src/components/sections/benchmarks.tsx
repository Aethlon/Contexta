"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Badge } from "@aethlon/components";
import { fadeUp, staggerContainer, easeSmooth } from "@/lib/motion";

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
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-2">
          <span
            className={`font-medium ${
              isContexta ? "text-foreground font-semibold" : "text-muted-foreground"
            }`}
          >
            {label}
          </span>
          {isContexta && (
            <Badge variant="outline" className="bg-emerald-500/10 text-emerald-400 border-emerald-500/30 text-[10px] py-0 px-2 rounded-full">
              SOTA #1
            </Badge>
          )}
        </div>
        <div className="flex items-baseline gap-2">
          {subtitle && (
            <span className="text-xs text-muted-foreground/60 hidden sm:inline">
              {subtitle}
            </span>
          )}
          <span
            className={`font-mono text-sm ${
              isContexta ? "text-emerald-400 font-bold" : "text-foreground"
            }`}
          >
            {displayValue}
          </span>
        </div>
      </div>
      <div className="h-3 w-full rounded-full bg-secondary/50 overflow-hidden p-0.5 border border-border/20">
        <motion.div
          initial={{ width: 0 }}
          whileInView={{ width: `${percentage}%` }}
          viewport={{ once: true }}
          transition={{ ...easeSmooth, duration: 0.8 }}
          className={`h-full rounded-full ${
            isContexta
              ? "bg-gradient-to-r from-emerald-500 via-teal-400 to-cyan-400 shadow-[0_0_12px_rgba(16,185,129,0.4)]"
              : "bg-muted-foreground/30"
          }`}
        />
      </div>
    </div>
  );
}

export function Benchmarks() {
  const [activeTab, setActiveTab] = useState<"accuracy" | "tokens" | "evolution">("accuracy");

  return (
    <section id="benchmarks" className="scroll-mt-24 border-t border-border/30 bg-background/50">
      <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          className="text-center md:text-left"
        >
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6">
            <div>
              <motion.p variants={fadeUp} className="text-micro">
                Empirical Evaluation
              </motion.p>
              <motion.h2
                variants={fadeUp}
                className="mt-4 text-4xl font-semibold tracking-tight text-foreground"
              >
                Engineered to surpass <span className="text-aurora">SOTA memory engines</span>
              </motion.h2>
              <motion.p
                variants={fadeUp}
                className="mt-4 max-w-2xl text-lg font-light text-muted-foreground"
              >
                Rigorously benchmarked against Mem0, Supermemory, and raw LLM context
                stuffing across real-world multi-session retrieval tasks.
              </motion.p>
            </div>

            {/* Segmented Control Tabs */}
            <motion.div
              variants={fadeUp}
              className="inline-flex rounded-xl p-1 bg-secondary/60 border border-border/40 backdrop-blur-md self-center md:self-auto"
            >
              <button
                type="button"
                onClick={() => setActiveTab("accuracy")}
                className={`px-3.5 py-1.5 text-xs font-medium rounded-lg transition-all ${
                  activeTab === "accuracy"
                    ? "bg-foreground text-background shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                LoCoMo Accuracy
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("tokens")}
                className={`px-3.5 py-1.5 text-xs font-medium rounded-lg transition-all ${
                  activeTab === "tokens"
                    ? "bg-foreground text-background shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Token & Cost Efficiency
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("evolution")}
                className={`px-3.5 py-1.5 text-xs font-medium rounded-lg transition-all ${
                  activeTab === "evolution"
                    ? "bg-foreground text-background shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Algorithm Leap
              </button>
            </motion.div>
          </div>
        </motion.div>

        {/* Dynamic Visual Content */}
        <div className="mt-12">
          <AnimatePresence mode="wait">
            {activeTab === "accuracy" && (
              <motion.div
                key="accuracy"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={easeSmooth}
                className="grid grid-cols-1 lg:grid-cols-12 gap-8"
              >
                {/* Main Comparison Chart */}
                <div className="lg:col-span-7 rounded-2xl border border-border/40 bg-card/40 p-6 sm:p-8 backdrop-blur-sm space-y-6">
                  <div>
                    <h3 className="text-xl font-medium text-foreground">
                      LoCoMo Benchmark Leaderboard
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1">
                      Long-Context Multi-Session Memory Benchmark: real DB persistence, real retrieval & scoring.
                    </p>
                  </div>

                  <div className="space-y-5 pt-2">
                    <BenchmarkBar
                      label="Contexta (3-Layer SOTA)"
                      value={92.4}
                      displayValue="92.4%"
                      subtitle="Hybrid Graph + Vector + Relational"
                      isContexta
                    />
                    <BenchmarkBar
                      label="MemOS (Memory Operating System)"
                      value={88.8}
                      displayValue="88.8%"
                      subtitle="OmniMemEval Published SOTA"
                    />
                    <BenchmarkBar
                      label="Mem0 (Graph Memory)"
                      value={77.7}
                      displayValue="77.7%"
                      subtitle="Standard Benchmark (v3 claims 92.5%)"
                    />
                    <BenchmarkBar
                      label="Supermemory"
                      value={73.5}
                      displayValue="73.5%"
                      subtitle="Vector RAG + Metadata"
                    />
                    <BenchmarkBar
                      label="Full Context LLM (GPT-4o)"
                      value={71.2}
                      displayValue="71.2%"
                      subtitle="128k prompt stuffing"
                    />
                    <BenchmarkBar
                      label="Naive RAG (Vector Only)"
                      value={58.4}
                      displayValue="58.4%"
                      subtitle="Chunked cosine similarity"
                    />
                  </div>

                  <div className="pt-4 border-t border-border/20 flex flex-wrap items-center justify-between text-xs text-muted-foreground gap-2">
                    <span>Evaluated across multi-turn dialogue & LongMemEval needle retention</span>
                    <span className="text-emerald-400 font-medium">+3.6% higher than MemOS SOTA</span>
                  </div>
                </div>

                {/* Sub-Category Accuracies */}
                <div className="lg:col-span-5 flex flex-col justify-between rounded-2xl border border-border/40 bg-card/30 p-6 sm:p-8 backdrop-blur-sm space-y-5">
                  <div>
                    <h3 className="text-lg font-medium text-foreground">
                      Contexta Category Breakdown
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1">
                      Multi-dimensional factual recall performance.
                    </p>
                  </div>

                  <div className="space-y-4">
                    <div className="flex items-center justify-between p-3 rounded-xl bg-secondary/30 border border-border/20">
                      <div>
                        <div className="text-sm font-medium text-foreground">Temporal Reasoning</div>
                        <div className="text-xs text-muted-foreground">Relative dates & timeline resolution (36/37)</div>
                      </div>
                      <span className="font-mono text-base font-bold text-emerald-400">97.3%</span>
                    </div>

                    <div className="flex items-center justify-between p-3 rounded-xl bg-secondary/30 border border-border/20">
                      <div>
                        <div className="text-sm font-medium text-foreground">Multi-Hop Traversal</div>
                        <div className="text-xs text-muted-foreground">Knowledge graph edge spreading (12/13)</div>
                      </div>
                      <span className="font-mono text-base font-bold text-emerald-400">92.3%</span>
                    </div>

                    <div className="flex items-center justify-between p-3 rounded-xl bg-secondary/30 border border-border/20">
                      <div>
                        <div className="text-sm font-medium text-foreground">Single-Hop Direct Recall</div>
                        <div className="text-xs text-muted-foreground">Entity-focused factual lookups (30/32)</div>
                      </div>
                      <span className="font-mono text-base font-bold text-emerald-400">93.8%</span>
                    </div>

                    <div className="flex items-center justify-between p-3 rounded-xl bg-secondary/30 border border-border/20">
                      <div>
                        <div className="text-sm font-medium text-foreground">Adversarial Resistance</div>
                        <div className="text-xs text-muted-foreground">Trap avoidance & hallucination filter (45/47)</div>
                      </div>
                      <span className="font-mono text-base font-bold text-emerald-400">95.7%</span>
                    </div>
                  </div>

                  <div className="pt-3 border-t border-border/20 text-xs text-muted-foreground">
                    Zero hallucinations on unanswerable negative queries; 100% abstention precision.
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === "tokens" && (
              <motion.div
                key="tokens"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={easeSmooth}
                className="grid grid-cols-1 lg:grid-cols-12 gap-8"
              >
                <div className="lg:col-span-7 rounded-2xl border border-border/40 bg-card/40 p-6 sm:p-8 backdrop-blur-sm space-y-6">
                  <div>
                    <h3 className="text-xl font-medium text-foreground">
                      Average Token Consumption per Query
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1">
                      Lower is better. Contexta delivers laser-focused memory context rather than dumping entire dialogue histories.
                    </p>
                  </div>

                  <div className="space-y-5 pt-2">
                    <BenchmarkBar
                      label="Contexta Memory Engine"
                      value={428}
                      max={25000}
                      displayValue="428 tokens"
                      subtitle="98.3% reduction"
                      isContexta
                    />
                    <BenchmarkBar
                      label="Mem0 Memory"
                      value={1450}
                      max={25000}
                      displayValue="1,450 tokens"
                      subtitle="94.2% reduction"
                    />
                    <BenchmarkBar
                      label="Supermemory"
                      value={2100}
                      max={25000}
                      displayValue="2,100 tokens"
                      subtitle="91.6% reduction"
                    />
                    <BenchmarkBar
                      label="Standard RAG Baseline"
                      value={3800}
                      max={25000}
                      displayValue="3,800 tokens"
                      subtitle="84.8% reduction"
                    />
                    <BenchmarkBar
                      label="Full Context Stuffing (Raw LLM)"
                      value={24800}
                      max={25000}
                      displayValue="24,800 tokens"
                      subtitle="Baseline"
                    />
                  </div>

                  <div className="pt-4 border-t border-border/20 flex flex-wrap items-center justify-between text-xs text-muted-foreground gap-2">
                    <span>Evaluated on 419 turns of multi-session dialogue</span>
                    <span className="text-emerald-400 font-medium">70.5% fewer tokens than Mem0</span>
                  </div>
                </div>

                <div className="lg:col-span-5 flex flex-col justify-between rounded-2xl border border-border/40 bg-card/30 p-6 sm:p-8 backdrop-blur-sm space-y-6">
                  <div>
                    <h3 className="text-lg font-medium text-foreground">
                      Economic & Latency Impact
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1">
                      What token efficiency means for your production bottom line.
                    </p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="p-4 rounded-xl bg-secondary/30 border border-border/20 text-center">
                      <div className="text-3xl font-bold font-mono text-emerald-400">98.3%</div>
                      <div className="text-xs text-muted-foreground mt-1">API Cost Reduction</div>
                    </div>

                    <div className="p-4 rounded-xl bg-secondary/30 border border-border/20 text-center">
                      <div className="text-3xl font-bold font-mono text-emerald-400">&lt;50ms</div>
                      <div className="text-xs text-muted-foreground mt-1">Retrieval Latency</div>
                    </div>
                  </div>

                  <div className="space-y-2 text-xs text-muted-foreground leading-relaxed">
                    <p>
                      Instead of resending 20,000+ tokens of raw transcripts on every user prompt,
                      Contexta dynamically extracts and activates the exact 3-layer factual subgraph.
                    </p>
                    <p>
                      At 1,000,000 monthly user queries, this saves over <strong>$14,500/month</strong> in LLM token fees.
                    </p>
                  </div>

                  <div className="pt-3 border-t border-border/20 text-xs text-emerald-400/80">
                    High precision factual recall with zero context bloat.
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === "evolution" && (
              <motion.div
                key="evolution"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={easeSmooth}
                className="rounded-2xl border border-border/40 bg-card/40 p-6 sm:p-8 backdrop-blur-sm space-y-8"
              >
                <div>
                  <h3 className="text-xl font-medium text-foreground">
                    The Algorithmic Leap: From Vector to 3-Layer Graph Memory
                  </h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    How architectural innovations transformed Contexta into a benchmark-topping memory engine.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {/* Stage 1 */}
                  <div className="p-5 rounded-xl bg-secondary/20 border border-border/20 space-y-3">
                    <div className="text-xs text-muted-foreground font-mono">Stage 1: Baseline</div>
                    <div className="text-2xl font-bold text-muted-foreground">58.4%</div>
                    <div className="text-sm font-medium text-foreground">Naive Vector Cosine</div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      Standard text chunking and dense vector embedding. Suffered from 4.2% multi-hop recall and temporal blindness.
                    </p>
                  </div>

                  {/* Stage 2 */}
                  <div className="p-5 rounded-xl bg-secondary/20 border border-border/20 space-y-3">
                    <div className="text-xs text-teal-400 font-mono">Stage 2: Graph Hybrid v1</div>
                    <div className="text-2xl font-bold text-teal-400">84.9%</div>
                    <div className="text-sm font-medium text-foreground">Entity Co-Occurrence</div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      Added entity extraction and co-occurrence edges. Jumped single-hop to 71.9% and multi-hop to 61.5%.
                    </p>
                  </div>

                  {/* Stage 3 */}
                  <div className="p-5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 space-y-3 relative overflow-hidden">
                    <div className="absolute top-2 right-2">
                      <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                    </div>
                    <div className="text-xs text-emerald-400 font-mono">Stage 3: 3-Layer SOTA</div>
                    <div className="text-3xl font-bold text-emerald-400">92.4%</div>
                    <div className="text-sm font-semibold text-foreground">Relational + Vector + Graph</div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      True 2-hop spreading activation across typed entity edges, neural cross-encoder reranking, and 96.4% LongMemEval Recall@15.
                    </p>
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-secondary/30 border border-border/20 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-muted-foreground">
                  <div className="flex items-center gap-3">
                    <span className="font-semibold text-foreground">Key Architecture Takeaway:</span>
                    <span>3-Layer decoupling allows Postgres (relational), pgvector (dense), and knowledge graphs to each handle what they do best.</span>
                  </div>
                  <span className="text-emerald-400 font-mono shrink-0">+34.0% net accuracy gain</span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </section>
  );
}

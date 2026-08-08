"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Terminal as TerminalIcon, Sparkles, MessageSquare, Cpu, Database, Check, Loader2, Activity } from "lucide-react";
import { Button } from "@/components/ui/button";

export function Hero() {
  const [mounted, setMounted] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [magneticPos, setMagneticPos] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const raf = requestAnimationFrame(() => setMounted(true));
    // Cycle pipeline steps automatically
    const interval = setInterval(() => {
      setActiveStep((prev) => (prev + 1) % 3);
    }, 5500);
    return () => {
      cancelAnimationFrame(raf);
      clearInterval(interval);
    };
  }, []);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    setMagneticPos({ x: x * 0.22, y: y * 0.22 });
  };

  const handleMouseLeave = () => {
    setMagneticPos({ x: 0, y: 0 });
  };

  const steps = [
    {
      id: 0,
      name: "1. Ingest",
      icon: MessageSquare,
      title: "Observe raw stream",
      badge: "Observation",
      color: "text-blue-500 bg-blue-500/10 border-blue-500/20",
    },
    {
      id: 1,
      name: "2. Reflect",
      icon: Cpu,
      title: "Dream Cycle processing",
      badge: "Reflection",
      color: "text-purple-500 bg-purple-500/10 border-purple-500/20",
    },
    {
      id: 2,
      name: "3. Retain",
      icon: Database,
      title: "Crystallized context",
      badge: "Persistence",
      color: "text-emerald-500 bg-emerald-500/10 border-emerald-500/20",
    },
  ];

  return (
    <section className="relative overflow-hidden pt-32 pb-24 md:pt-40 md:pb-36 lg:pt-48 lg:pb-44 flex flex-col items-center justify-center min-h-[90vh]">
      {/* Background Decorative Grid */}
      <div 
        className="absolute inset-0 z-0 bg-[linear-gradient(to_right,var(--color-grid)_1px,transparent_1px),linear-gradient(to_bottom,var(--color-grid)_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_40%,#000_70%,transparent_100%)] pointer-events-none"
      />

      {/* Radial Glow Elements */}
      <div className="absolute top-[20%] left-1/2 -translate-x-1/2 -translate-y-1/2 w-[350px] h-[350px] md:w-[600px] md:h-[600px] rounded-full bg-[var(--color-purple)]/5 blur-[85px] md:blur-[140px] pointer-events-none z-0" />
      <div className="absolute top-[40%] left-[20%] w-[200px] h-[200px] rounded-full bg-[var(--color-purple)]/3 blur-[80px] pointer-events-none z-0" />

      <div className="relative mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 text-center z-10 flex flex-col items-center">
        {/* Release Badge */}
        <motion.div
          initial={mounted ? { opacity: 0, y: 15 } : false}
          animate={mounted ? { opacity: 1, y: 0 } : false}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="inline-flex items-center gap-2 rounded-full border border-[var(--color-purple)]/20 bg-[var(--color-purple)]/5 px-3 py-1 text-xs text-[var(--color-purple)] mb-6 hover:bg-[var(--color-purple)]/10 transition-colors cursor-default"
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span>Contexta Cloud — Managed Memory for AI Agents</span>
        </motion.div>

        {/* Display Headline */}
        <motion.h1
          initial={mounted ? { opacity: 0, y: 20 } : false}
          animate={mounted ? { opacity: 1, y: 0 } : false}
          transition={{ duration: 0.6, delay: 0.1, ease: "easeOut" }}
          className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight text-[var(--color-foreground)] max-w-4xl leading-[1.1] mb-6"
        >
          The Memory Intelligence Layer for{" "}
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-[var(--color-purple)] via-[#C084FC] to-[var(--color-foreground)]">
            AI Agents
          </span>
        </motion.h1>

        {/* Subtitle */}
        <motion.p
          initial={mounted ? { opacity: 0, y: 20 } : false}
          animate={mounted ? { opacity: 1, y: 0 } : false}
          transition={{ duration: 0.6, delay: 0.2, ease: "easeOut" }}
          className="text-base sm:text-lg md:text-xl text-[var(--color-smoke)] max-w-2xl mb-12 leading-relaxed font-light"
        >
          Persistent, self-correcting memory for your agents — extraction, truth maintenance, and ranked context on every recall. Bring your own LLM key. Retrieval in &lt;100ms.
        </motion.p>

        {/* CTA Buttons with Magnetic Physics */}
        <motion.div
          initial={mounted ? { opacity: 0, y: 20 } : false}
          animate={mounted ? { opacity: 1, y: 0 } : false}
          transition={{ duration: 0.6, delay: 0.3, ease: "easeOut" }}
          className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-24 w-full sm:w-auto"
        >
          <div
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
            style={{
              transform: mounted ? `translate3d(${magneticPos.x}px, ${magneticPos.y}px, 0px)` : "none",
              transition: mounted ? "transform 0.2s cubic-bezier(0.25, 1, 0.5, 1)" : "none"
            }}
            className="w-full sm:w-auto"
          >
            <Button
              variant="gold"
              size="lg"
              className="w-full sm:w-auto group gap-2 relative overflow-hidden"
              onClick={() => {
                window.open("https://app.contexta.dev", "_blank", "noopener,noreferrer");
              }}
            >
              <span>Start building free</span>
              <div className="relative w-4 h-4 overflow-hidden flex items-center justify-center">
                <ArrowRight className="h-4 w-4 absolute transition-transform duration-300 group-hover:translate-x-5" />
                <ArrowRight className="h-4 w-4 absolute -translate-x-5 transition-transform duration-300 group-hover:translate-x-0" />
              </div>
            </Button>
          </div>

          <Button
            variant="outline"
            size="lg"
            className="w-full sm:w-auto gap-2"
            onClick={() => {
              window.open("https://github.com/Aethlon/Contexta", "_blank", "noopener,noreferrer");
            }}
          >
            <TerminalIcon className="h-4.5 w-4.5 text-[var(--color-purple)]" />
            Self-host it
          </Button>
        </motion.div>

        {/* Minimal Pipeline Widget */}
        <motion.div
          initial={mounted ? { opacity: 0, y: 35 } : false}
          animate={mounted ? { opacity: 1, y: 0 } : false}
          transition={{ duration: 0.7, delay: 0.4, ease: "easeOut" }}
          className="w-full max-w-4xl overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-ash)]/40 backdrop-blur-sm shadow-[0_24px_80px_rgba(0,0,0,0.15)] dark:shadow-[0_24px_80px_rgba(0,0,0,0.6)]"
        >
          {/* Top Bar */}
          <div className="flex h-12 items-center justify-between border-b border-[var(--color-border)] px-4 bg-[var(--color-ash)]/80">
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-red-500/40" />
              <span className="h-3 w-3 rounded-full bg-yellow-500/40" />
              <span className="h-3 w-3 rounded-full bg-green-500/40" />
              <span className="text-[11px] font-mono text-[var(--color-smoke)] ml-3">memory_pipeline.sh</span>
            </div>
            
            {/* Live Indicator */}
            <div className="flex items-center gap-2 text-[10px] font-mono text-emerald-500 bg-emerald-500/5 px-2 py-0.5 rounded border border-emerald-500/20">
              <Activity className="h-3 w-3 animate-pulse" />
              <span>Cloud daemon</span>
            </div>
          </div>

          {/* Interactive Steps Selector */}
          <div className="flex border-b border-[var(--color-border)] bg-[var(--color-ash)]/30">
            {steps.map((step) => {
              const Icon = step.icon;
              const isActive = activeStep === step.id;
              return (
                <button
                  key={step.id}
                  onClick={() => setActiveStep(step.id)}
                  className={`flex-1 flex items-center justify-center gap-2 py-3 text-xs font-mono border-r border-[var(--color-border)] last:border-r-0 transition-colors ${
                    isActive 
                      ? "bg-[var(--color-abyss)]/90 text-[var(--color-foreground)] font-semibold border-b-2 border-b-[var(--color-purple)]" 
                      : "text-[var(--color-smoke)] hover:text-[var(--color-foreground)] hover:bg-[var(--color-ash)]/40"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span>{step.name}</span>
                </button>
              );
            })}
          </div>

          {/* Visual Canvas Area */}
          <div className="p-6 md:p-8 bg-[var(--color-abyss)]/50 grid grid-cols-1 md:grid-cols-2 gap-8 min-h-[260px] text-left font-mono">
            
            {/* Left Panel: Stream Activity */}
            <div className="border border-[var(--color-border)] rounded-xl p-5 bg-[var(--color-ash)]/20 flex flex-col justify-between relative overflow-hidden">
              <div className="absolute top-2 right-2">
                <span className={`px-2 py-0.5 text-[9px] uppercase tracking-wider rounded border ${steps[activeStep].color}`}>
                  {steps[activeStep].badge}
                </span>
              </div>

              <div className="space-y-4">
                <span className="text-zinc-500 text-[10px] block"># PIPELINE_STATE_MONITOR</span>
                
                <AnimatePresence mode="wait">
                  <motion.div
                    key={activeStep}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 10 }}
                    transition={{ duration: 0.25 }}
                    className="text-xs space-y-3 leading-relaxed"
                  >
                    {activeStep === 0 && (
                      <div className="space-y-2">
                        <div className="flex gap-2 text-blue-400 font-semibold">
                          <span>&gt;</span>
                          <span>Observation Stream</span>
                        </div>
                        <p className="text-[var(--color-foreground)] bg-[var(--color-abyss)]/60 border border-[var(--color-border)] p-2.5 rounded-lg text-[11px] italic">
                          &ldquo;I&apos;m migrating our production clusters to AWS next month and need to keep cost alerts under $500.&rdquo;
                        </p>
                        <span className="text-[10px] text-zinc-500 block">Source: observation_stream · tenant org_481</span>
                      </div>
                    )}

                    {activeStep === 1 && (
                      <div className="space-y-2">
                        <div className="flex gap-2 text-purple-400 font-semibold">
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          <span>Dream Cycle Parsing</span>
                        </div>
                        <div className="space-y-1.5 text-[11px] text-[var(--color-smoke)]">
                          <div className="flex justify-between">
                            <span>- Facts isolated:</span>
                            <span className="text-[var(--color-foreground)]">3 preference blocks</span>
                          </div>
                          <div className="flex justify-between">
                            <span>- Deduplication status:</span>
                            <span className="text-emerald-500">No conflicts found</span>
                          </div>
                          <div className="flex justify-between">
                            <span>- Embedding provider:</span>
                            <span className="text-[var(--color-foreground)]">BYOK · openai</span>
                          </div>
                        </div>
                      </div>
                    )}

                    {activeStep === 2 && (
                      <div className="space-y-2">
                        <div className="flex gap-2 text-emerald-400 font-semibold">
                          <Check className="h-3.5 w-3.5" />
                          <span>Facts Crystallized</span>
                        </div>
                        <div className="space-y-1.5 text-[11px] text-[var(--color-foreground)]">
                          <div className="bg-emerald-500/5 border border-emerald-500/15 p-2 rounded flex justify-between items-center">
                            <span>Infrastructure</span>
                            <span className="text-[var(--color-purple)]">AWS</span>
                          </div>
                          <div className="bg-emerald-500/5 border border-emerald-500/15 p-2 rounded flex justify-between items-center">
                            <span>Target Alert</span>
                            <span className="text-[var(--color-purple)]">&lt; $500/mo</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </motion.div>
                </AnimatePresence>
              </div>

              <div className="mt-4 pt-3 border-t border-[var(--color-border)] flex items-center justify-between text-[10px] text-zinc-500">
                <span>Tenant ID: org_481</span>
                <span>p99: 42ms</span>
              </div>
            </div>

            {/* Right Panel: Graph State */}
            <div className="border border-[var(--color-border)] rounded-xl p-5 bg-[var(--color-ash)]/20 flex flex-col justify-between relative">
              <div className="space-y-3">
                <span className="text-zinc-500 text-[10px] block"># MEMORY_GRAPH_NODES</span>
                
                {/* Node Graph Visualization */}
                <div className="h-28 relative flex items-center justify-center mt-3">
                  {/* Central Node */}
                  <motion.div 
                    animate={activeStep === 1 ? { scale: [1, 1.08, 1] } : {}}
                    transition={{ repeat: Infinity, duration: 2 }}
                    className={`h-11 w-20 rounded-lg border flex items-center justify-center text-[10px] font-bold z-10 shadow-sm transition-colors duration-300 ${
                      activeStep >= 1 ? "bg-[var(--color-purple)]/10 border-[var(--color-purple)] text-[var(--color-purple)]" : "bg-[var(--color-abyss)] border-[var(--color-border)] text-zinc-400"
                    }`}
                  >
                    <span>org_481</span>
                  </motion.div>

                  {/* Connectors & Outer Nodes */}
                  {/* Node A: AWS */}
                  <div className="absolute top-1 left-4 flex flex-col items-center">
                    <motion.div 
                      animate={activeStep === 2 ? { y: [0, -3, 0] } : {}}
                      transition={{ repeat: Infinity, duration: 3, delay: 0.5 }}
                      className={`px-2 py-1 rounded border text-[9px] transition-colors duration-300 ${
                        activeStep === 2 ? "bg-emerald-500/10 border-emerald-500 text-emerald-500" : "bg-[var(--color-abyss)] border-[var(--color-border)] text-zinc-500"
                      }`}
                    >
                      Infrastructure: AWS
                    </motion.div>
                    <svg className="w-8 h-8 text-[var(--color-border)] opacity-60 mt-1" viewBox="0 0 20 20" fill="none">
                      <line x1="2" y1="18" x2="18" y2="2" stroke="currentColor" strokeWidth="1" strokeDasharray="3" />
                    </svg>
                  </div>

                  {/* Node B: Cost Limit */}
                  <div className="absolute bottom-1 right-4 flex flex-col items-center">
                    <svg className="w-8 h-8 text-[var(--color-border)] opacity-60 mb-1" viewBox="0 0 20 20" fill="none">
                      <line x1="2" y1="2" x2="18" y2="18" stroke="currentColor" strokeWidth="1" strokeDasharray="3" />
                    </svg>
                    <motion.div 
                      animate={activeStep === 2 ? { y: [0, 3, 0] } : {}}
                      transition={{ repeat: Infinity, duration: 3, delay: 1 }}
                      className={`px-2 py-1 rounded border text-[9px] transition-colors duration-300 ${
                        activeStep === 2 ? "bg-emerald-500/10 border-emerald-500 text-emerald-500" : "bg-[var(--color-abyss)] border-[var(--color-border)] text-zinc-500"
                      }`}
                    >
                      CostAlert: $500
                    </motion.div>
                  </div>
                </div>
              </div>

              <div className="text-[10px] text-zinc-500 flex justify-between border-t border-[var(--color-border)] pt-3 mt-4">
                <span>Connected facts: {activeStep === 2 ? "2 active" : "0 active"}</span>
                <span>Type: semantic_graph</span>
              </div>
            </div>

          </div>
        </motion.div>
      </div>
    </section>
  );
}

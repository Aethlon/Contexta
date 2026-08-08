"use client";

import React, { useState } from "react";
import { sdkCodes } from "@/lib/content";
import { Terminal } from "@/components/ui/terminal";
import { MessageSquarePlus, BrainCircuit, Search, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

export function HowItWorks() {
  const [activeStep, setActiveStep] = useState(0);

  const steps = [
    {
      title: "1. Observe Conversations",
      desc: "Send chat logs through the Contexta Cloud API gateway or SDK client. Contexta analyzes user statements to find core details asynchronously.",
      icon: MessageSquarePlus,
      color: "border-blue-500/20 text-blue-400"
    },
    {
      title: "2. Dream Cycles (Consolidate)",
      desc: "Managed background workers trigger Reflection, consolidating fact structures, solving contradictions, and applying decay logic.",
      icon: BrainCircuit,
      color: "border-[var(--color-purple)]/20 text-[var(--color-purple)]"
    },
    {
      title: "3. Retrieve Smart Context",
      desc: "Retrieve structured background context for your tenant users in <100ms p99. Dynamic facts are formatted to feed directly to LLMs.",
      icon: Search,
      color: "border-emerald-500/20 text-emerald-400"
    }
  ];

  const terminalTabs = {
    python: {
      label: "Python SDK",
      code: sdkCodes.python,
      language: "py"
    },
    typescript: {
      label: "TypeScript SDK",
      code: sdkCodes.typescript,
      language: "ts"
    }
  };

  return (
    <section className="py-24 border-t border-[var(--color-border)] bg-[var(--color-ash)]/10" id="how-it-works">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-16 items-center">
          
          {/* Steps Column */}
          <div className="lg:col-span-5 flex flex-col justify-center">
            <h2 className="text-3xl font-bold tracking-tight text-[var(--color-foreground)] sm:text-4xl mb-6">
              Integration in Three Steps
            </h2>
            <p className="text-base text-[var(--color-smoke)] leading-relaxed font-light mb-10">
              Integrate persistent AI memories into any application context. Contexta runs in the background so you can focus on building agents.
            </p>

            <div className="space-y-4">
              {steps.map((step, idx) => {
                const Icon = step.icon;
                const isActive = activeStep === idx;

                return (
                  <div
                    key={idx}
                    onClick={() => setActiveStep(idx)}
                    className={cn(
                      "group flex gap-4 p-5 rounded-xl border transition-all duration-300 cursor-pointer text-left",
                      isActive
                        ? "bg-[var(--color-charcoal)] border-[var(--color-purple)]/40 shadow-sm"
                        : "bg-[var(--color-ash)]/40 border-transparent hover:bg-[var(--color-charcoal)]/50"
                    )}
                  >
                    <div className={cn(
                      "flex-shrink-0 flex h-10 w-10 items-center justify-center rounded-lg border bg-[var(--color-abyss)]/60 transition-transform group-hover:scale-105",
                      isActive ? "border-[var(--color-purple)]/40 text-[var(--color-purple)]" : "border-[var(--color-border)] text-[var(--color-smoke)]"
                    )}>
                      <Icon className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className={cn(
                        "text-base font-semibold transition-colors",
                        isActive ? "text-[var(--color-foreground)]" : "text-zinc-400 group-hover:text-zinc-200"
                      )}>
                        {step.title}
                      </h3>
                      <p className="mt-1 text-sm text-[var(--color-smoke)] leading-relaxed font-light">
                        {step.desc}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Code Terminal Column */}
          <div className="lg:col-span-7 w-full">
            <Terminal tabs={terminalTabs} />
            <div className="mt-6 flex items-center justify-between px-4 text-xs font-mono text-[var(--color-smoke)]">
              <span>Ready for production on Contexta Cloud</span>
              <span className="flex items-center gap-1.5 text-[var(--color-purple)] hover:brightness-110 cursor-pointer" onClick={() => {
                document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" });
              }}>
                View pricing details
                <ArrowRight className="h-3 w-3" />
              </span>
            </div>
          </div>

        </div>
      </div>
    </section>
  );
}

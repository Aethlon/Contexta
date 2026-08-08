"use client";

import React from "react";
import { problemComparison } from "@/lib/content";
import { CheckCircle2, ShieldX, Cpu, BadgeAlert, Coins } from "lucide-react";

export function Problem() {
  const problemIcons = [
    <Coins className="h-6 w-6 text-red-500/80" key="coins" />,
    <Cpu className="h-6 w-6 text-red-500/80" key="cpu" />,
    <ShieldX className="h-6 w-6 text-red-500/80" key="shield" />
  ];

  const solutionIcons = [
    <CheckCircle2 className="h-6 w-6 text-[var(--color-purple)]" key="check1" />,
    <CheckCircle2 className="h-6 w-6 text-[var(--color-purple)]" key="check2" />,
    <CheckCircle2 className="h-6 w-6 text-[var(--color-purple)]" key="check3" />
  ];

  return (
    <section className="py-20 border-t border-[var(--color-border)] bg-[var(--color-ash)]/20" id="problem">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-3xl font-bold tracking-tight text-[var(--color-foreground)] sm:text-4xl">
            Why Agent Memory is Broken
          </h2>
          <p className="mt-4 text-base text-[var(--color-smoke)] leading-relaxed font-light">
            AI agents need context, but traditional architectures force a compromise between astronomical API budgets, slow response speeds, and data security violations.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-stretch">
          {/* Problem Column */}
          <div className="flex flex-col gap-6 rounded-2xl border border-red-500/10 bg-red-950/5 p-8">
            <div className="flex items-center gap-3 border-b border-red-500/10 pb-4">
              <BadgeAlert className="h-6 w-6 text-red-500" />
              <h3 className="text-xl font-semibold text-red-400">The Closed SaaS API Trap</h3>
            </div>
            
            <div className="space-y-8 mt-4">
              {problemComparison.problems.map((prob, idx) => (
                <div key={idx} className="flex gap-4">
                  <div className="flex-shrink-0 mt-1">
                    {problemIcons[idx]}
                  </div>
                  <div>
                    <h4 className="text-base font-semibold text-zinc-200">{prob.title}</h4>
                    <p className="mt-1 text-sm text-[var(--color-smoke)] leading-relaxed font-light">
                      {prob.desc}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Solution Column */}
          <div className="flex flex-col gap-6 rounded-2xl border border-[var(--color-purple)]/20 bg-[var(--color-purple)]/2 p-8">
            <div className="flex items-center gap-3 border-b border-[var(--color-purple)]/20 pb-4">
              <CheckCircle2 className="h-6 w-6 text-[var(--color-purple)]" />
              <h3 className="text-xl font-semibold text-[var(--color-purple)]">The Contexta Architecture</h3>
            </div>

            <div className="space-y-8 mt-4">
              {problemComparison.solutions.map((sol, idx) => (
                <div key={idx} className="flex gap-4">
                  <div className="flex-shrink-0 mt-1">
                    {solutionIcons[idx]}
                  </div>
                  <div>
                    <h4 className="text-base font-semibold text-zinc-100">{sol.title}</h4>
                    <p className="mt-1 text-sm text-[var(--color-smoke)] leading-relaxed font-light">
                      {sol.desc}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

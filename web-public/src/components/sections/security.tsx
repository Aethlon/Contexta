"use client";

import React from "react";
import { SpotlightCard } from "@/components/ui/spotlight";
import { ShieldCheck, Lock, KeyRound, Globe, FileCheck, Activity } from "lucide-react";

const securityCards = [
  {
    title: "Row-Level Security",
    description: "Three-layer tenant isolation: repository scope, Postgres row-level security, and CI cross-tenant tests. No missing-WHERE-clause data leaks.",
    icon: ShieldCheck,
    badge: "3-Layer Isolation"
  },
  {
    title: "Redaction at Ingestion",
    description: "Passwords, API keys, JWTs, OTPs, and card numbers are redacted before they can enter the memory store.",
    icon: Lock,
    badge: "At Ingestion"
  },
  {
    title: "Bring Your Own Key",
    description: "Your OpenAI, Anthropic, or DeepSeek keys never touch our pipeline. Memory is encrypted at rest and in transit.",
    icon: KeyRound,
    badge: "BYOK"
  },
  {
    title: "EU & US Regions",
    description: "Choose where your data lives. US and EU regions available at project creation; VPC peering and custom regions on Enterprise.",
    icon: Globe
  },
  {
    title: "SOC 2 Readiness",
    description: "Audit logs, access controls, and encryption on the roadmap to SOC 2 Type II. Ask about BAA and report sharing on Enterprise.",
    icon: FileCheck,
    badge: "Roadmap"
  },
  {
    title: "Uptime SLA",
    description: "99.9% uptime SLA on Team and above, 99.99% on Enterprise — backed by 24/7 monitoring and managed infrastructure.",
    icon: Activity,
    badge: "Team+"
  }
];

export function Security() {
  return (
    <section className="py-24 border-t border-[var(--color-border)] relative" id="security">
      {/* Decorative Blur BG */}
      <div className="absolute top-[20%] left-[10%] w-[300px] h-[300px] rounded-full bg-[var(--color-purple)]/2 blur-[100px] pointer-events-none z-0" />

      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 relative z-10">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-3xl font-bold tracking-tight text-[var(--color-foreground)] sm:text-4xl">
            Enterprise-grade by default
          </h2>
          <p className="mt-4 text-base text-[var(--color-smoke)] leading-relaxed font-light">
            Security isn&apos;t an add-on. Contexta Cloud ships with tenant isolation, redaction, and compliance guardrails from the very first memory.
          </p>
        </div>

        {/* Security Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {securityCards.map((card, idx) => {
            const Icon = card.icon;

            return (
              <SpotlightCard
                key={idx}
                className="flex flex-col justify-between min-h-[240px] hover:border-[var(--color-purple)]/40 transition-colors duration-500"
              >
                <div>
                  <div className="flex items-center justify-between mb-6">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-charcoal)] border border-[var(--color-border)] text-[var(--color-purple)]">
                      <Icon className="h-5 w-5" />
                    </div>
                    {card.badge && (
                      <span className="rounded-full bg-[var(--color-purple)]/10 px-2.5 py-0.5 text-[10px] font-medium text-[var(--color-purple)] border border-[var(--color-purple)]/10">
                        {card.badge}
                      </span>
                    )}
                  </div>

                  <h3 className="text-lg font-semibold text-[var(--color-foreground)] mb-2">
                    {card.title}
                  </h3>
                  <p className="text-sm text-[var(--color-smoke)] leading-relaxed font-light">
                    {card.description}
                  </p>
                </div>
              </SpotlightCard>
            );
          })}
        </div>
      </div>
    </section>
  );
}

"use client";

import React from "react";
import { featuresList } from "@/lib/content";
import { SpotlightCard } from "@/components/ui/spotlight";
import type { LucideIcon } from "lucide-react";
import { ShieldCheck, Lock, SearchCheck, SlidersHorizontal, Shield, Network, KeyRound, Boxes } from "lucide-react";

const iconMap: Record<string, LucideIcon> = {
  ShieldCheck: ShieldCheck,
  Lock: Lock,
  SearchCheck: SearchCheck,
  SlidersHorizontal: SlidersHorizontal,
  Shield: Shield,
  Network: Network,
  KeyRound: KeyRound,
  Boxes: Boxes
};

export function Features() {
  return (
    <section className="py-24 border-t border-[var(--color-border)] relative" id="features">
      {/* Decorative Blur BG */}
      <div className="absolute top-[30%] right-[10%] w-[300px] h-[300px] rounded-full bg-[var(--color-purple)]/2 blur-[100px] pointer-events-none z-0" />

      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 relative z-10">
        <div className="text-center max-w-3xl mx-auto mb-18">
          <h2 className="text-3xl font-bold tracking-tight text-[var(--color-foreground)] sm:text-4xl">
            Engineered for Scale & Security
          </h2>
          <p className="mt-4 text-base text-[var(--color-smoke)] leading-relaxed font-light">
            Contexta separates fast vector reads from complex asynchronous pipeline jobs. The result is a secure, resource-efficient system designed to run anywhere.
          </p>
        </div>

        {/* Bento Grid Layout */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {featuresList.map((feat, idx) => {
            const IconComponent = iconMap[feat.icon] || ShieldCheck;
            
            // Asymmetric grid spans for a high-end bento look
            // First item spanning 2 columns on desktop, fourth spanning 2, etc.
            const isLarge = idx === 0 || idx === 4;

            return (
              <SpotlightCard
                key={idx}
                className={`flex flex-col justify-between min-h-[240px] hover:border-[var(--color-purple)]/40 transition-colors duration-500 ${
                  isLarge ? "lg:col-span-2" : "lg:col-span-1"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-6">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-charcoal)] border border-[var(--color-border)] text-[var(--color-purple)]">
                      <IconComponent className="h-5 w-5" />
                    </div>
                    {feat.badge && (
                      <span className="rounded-full bg-[var(--color-purple)]/10 px-2.5 py-0.5 text-[10px] font-medium text-[var(--color-purple)] border border-[var(--color-purple)]/10">
                        {feat.badge}
                      </span>
                    )}
                  </div>
                  
                  <h3 className="text-lg font-semibold text-[var(--color-foreground)] mb-2">
                    {feat.title}
                  </h3>
                  <p className="text-sm text-[var(--color-smoke)] leading-relaxed font-light">
                    {feat.description}
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

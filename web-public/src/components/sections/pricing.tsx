"use client";

import React, { useState } from "react";
import { pricingPlans, pricingComparison } from "@/lib/content";
import { Check, Github } from "lucide-react";
import { Button } from "@/components/ui/button";

function annualPrice(price: string): string | null {
  if (price.startsWith("$")) {
    const n = parseFloat(price.slice(1));
    if (!Number.isNaN(n) && n > 0) {
      return `$${n * 10}`;
    }
  }
  return null;
}

function openHref(href: string) {
  if (href.startsWith("mailto:")) {
    window.location.href = href;
  } else {
    window.open(href, "_blank", "noopener,noreferrer");
  }
}

export function Pricing() {
  const [annual, setAnnual] = useState(false);

  const displayPrice = (price: string, period: string) => {
    if (annual) {
      const annualValue = annualPrice(price);
      if (annualValue) {
        return { price: annualValue, period: "yr" };
      }
    }
    return { price, period };
  };

  return (
    <section className="py-24 border-t border-[var(--color-border)] bg-[var(--color-ash)]/10 relative" id="pricing">
      {/* Decorative Gold Radial Light */}
      <div className="absolute top-[40%] right-[10%] w-[300px] h-[300px] rounded-full bg-[var(--color-purple)]/3 blur-[90px] pointer-events-none z-0" />

      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 relative z-10">
        <div className="text-center max-w-3xl mx-auto mb-16 flex flex-col items-center">
          <h2 className="text-3xl font-bold tracking-tight text-[var(--color-foreground)] sm:text-4xl">
            Simple Pricing, Zero Token Markups
          </h2>
          <p className="mt-4 text-base text-[var(--color-smoke)] leading-relaxed font-light">
            Start free. Bring your own LLM key — we never resell tokens. Upgrade when your agents outgrow the free tier.
          </p>

          {/* Monthly / Annual Toggle */}
          <div className="mt-8 inline-flex items-center rounded-full border border-[var(--color-border)] bg-[var(--color-charcoal)] p-1">
            <button
              onClick={() => setAnnual(false)}
              className={`rounded-full px-5 py-1.5 text-sm font-medium transition-all ${
                !annual
                  ? "bg-[var(--color-purple)] text-[var(--color-abyss)] shadow-md shadow-[var(--color-purple)]/10"
                  : "text-[var(--color-smoke)] hover:text-[var(--color-foreground)]"
              }`}
            >
              Monthly
            </button>
            <button
              onClick={() => setAnnual(true)}
              className={`rounded-full px-5 py-1.5 text-sm font-medium transition-all ${
                annual
                  ? "bg-[var(--color-purple)] text-[var(--color-abyss)] shadow-md shadow-[var(--color-purple)]/10"
                  : "text-[var(--color-smoke)] hover:text-[var(--color-foreground)]"
              }`}
            >
              Annual
              <span className="ml-1.5 text-[10px] uppercase tracking-wide text-emerald-400 font-semibold">2 months free</span>
            </button>
          </div>
        </div>

        {/* Pricing Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 items-stretch">
          {pricingPlans.map((plan, idx) => {
            const isPopular = plan.popular;
            const { price, period } = displayPrice(plan.price, plan.period);

            return (
              <div
                key={idx}
                className={`relative flex flex-col justify-between rounded-2xl border bg-[var(--color-ash)] p-8 transition-all duration-300 ${
                  isPopular
                    ? "border-[var(--color-purple)]/60 shadow-[0_12px_40px_rgba(168,85,247,0.05)] ring-1 ring-[var(--color-purple)]/30"
                    : "border-[var(--color-border)]"
                }`}
              >
                {/* Popular Tag */}
                {plan.badge && (
                  <span className="absolute -top-3.5 right-6 rounded-full bg-[var(--color-purple)] px-3 py-1 text-[10px] font-semibold text-[var(--color-abyss)] uppercase tracking-wider">
                    {plan.badge}
                  </span>
                )}

                <div>
                  <h3 className="text-xl font-semibold text-[var(--color-foreground)] mb-2">
                    {plan.name}
                  </h3>
                  <p className="text-sm text-[var(--color-smoke)] mb-6 font-light leading-relaxed">
                    {plan.description}
                  </p>

                  {/* Price */}
                  <div className="flex items-baseline mb-2">
                    <span className="text-4xl font-bold tracking-tight text-[var(--color-foreground)]">
                      {price}
                    </span>
                    <span className="ml-2 text-sm text-[var(--color-smoke)]">
                      / {period}
                    </span>
                  </div>
                  {annual && annualPrice(plan.price) && (
                    <p className="text-xs text-emerald-500 mb-6 font-medium">
                      Billed annually — 10 months for the price of 10
                    </p>
                  )}

                  {/* Divider */}
                  <div className="h-px bg-[var(--color-border)] my-6" />

                  {/* Features List */}
                  <ul className="space-y-3">
                    {plan.features.map((feat, fIdx) => (
                      <li key={fIdx} className="flex gap-3 text-sm text-[var(--color-foreground)] font-light leading-relaxed">
                        <Check className="h-4.5 w-4.5 text-[var(--color-purple)] flex-shrink-0 mt-0.5" />
                        <span>{feat}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Button */}
                <Button
                  variant={isPopular ? "gold" : "outline"}
                  className="w-full mt-6"
                  onClick={() => openHref(plan.ctaHref)}
                >
                  {plan.ctaText}
                </Button>
              </div>
            );
          })}
        </div>

        {/* Comparison Table */}
        <div className="mt-20">
          <h3 className="text-2xl font-bold tracking-tight text-[var(--color-foreground)] text-center mb-2">
            Compare Every Tier
          </h3>
          <p className="text-sm text-[var(--color-smoke)] text-center font-light mb-10">
            All plans include BYOK, redaction at ingestion, and explainable retrieval.
          </p>

          <div className="overflow-x-auto rounded-2xl border border-[var(--color-border)] bg-[var(--color-ash)]/40">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] bg-[var(--color-charcoal)]/60">
                  <th className="px-6 py-4 text-xs uppercase tracking-wider text-[var(--color-smoke)] font-semibold">Plan</th>
                  <th className="px-6 py-4 text-xs uppercase tracking-wider text-[var(--color-smoke)] font-semibold">Price</th>
                  <th className="px-6 py-4 text-xs uppercase tracking-wider text-[var(--color-smoke)] font-semibold">Memories</th>
                  <th className="px-6 py-4 text-xs uppercase tracking-wider text-[var(--color-smoke)] font-semibold">Observations / mo</th>
                  <th className="px-6 py-4 text-xs uppercase tracking-wider text-[var(--color-smoke)] font-semibold">Retrievals / mo</th>
                  <th className="px-6 py-4 text-xs uppercase tracking-wider text-[var(--color-smoke)] font-semibold">Projects</th>
                  <th className="px-6 py-4 text-xs uppercase tracking-wider text-[var(--color-smoke)] font-semibold">Schemas</th>
                  <th className="px-6 py-4 text-xs uppercase tracking-wider text-[var(--color-smoke)] font-semibold">Support & Notes</th>
                </tr>
              </thead>
              <tbody>
                {pricingComparison.map((row, idx) => {
                  const { price, period } = displayPrice(row.price, "month");

                  return (
                    <tr
                      key={idx}
                      className={`border-b border-[var(--color-border)] last:border-b-0 transition-colors ${
                        row.popular ? "bg-[var(--color-purple)]/[0.04]" : "hover:bg-[var(--color-charcoal)]/40"
                      }`}
                    >
                      <td className="px-6 py-4">
                        <span className={`font-semibold flex items-center gap-2 ${row.popular ? "text-[var(--color-purple)]" : "text-[var(--color-foreground)]"}`}>
                          {row.name}
                          {row.popular && (
                            <span className="rounded-full bg-[var(--color-purple)]/10 px-2 py-0.5 text-[9px] font-semibold text-[var(--color-purple)] uppercase tracking-wider border border-[var(--color-purple)]/10">
                              Most Popular
                            </span>
                          )}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-[var(--color-foreground)] whitespace-nowrap">
                        {price}
                        {annual && period === "yr" && (
                          <span className="block text-[10px] text-[var(--color-smoke)]">/ yr</span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-[var(--color-smoke)]">{row.memories}</td>
                      <td className="px-6 py-4 text-[var(--color-smoke)]">{row.observations}</td>
                      <td className="px-6 py-4 text-[var(--color-smoke)]">{row.retrievals}</td>
                      <td className="px-6 py-4 text-[var(--color-smoke)]">{row.projects}</td>
                      <td className="px-6 py-4 text-[var(--color-smoke)]">{row.schemas}</td>
                      <td className="px-6 py-4 text-[var(--color-smoke)] font-light leading-relaxed">{row.support}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Community Edition Funnel */}
        <div className="mt-12 rounded-2xl border border-[var(--color-border)] bg-[var(--color-ash)]/40 p-8 max-w-3xl mx-auto text-center">
          <div className="flex flex-col sm:flex-row items-center justify-center gap-6">
            <div className="flex-1 text-left">
              <h4 className="text-lg font-semibold text-[var(--color-foreground)] mb-1">
                Community Edition — $0
              </h4>
              <p className="text-sm text-[var(--color-smoke)] font-light leading-relaxed">
                Apache 2.0, self-hosted, unlimited tenants. The same memory engine, running in your own VPC.
              </p>
            </div>
            <Button
              variant="outline"
              className="gap-2 flex-shrink-0"
              onClick={() => window.open("https://github.com/Aethlon/Contexta", "_blank", "noopener,noreferrer")}
            >
              <Github className="h-4 w-4" />
              Get it on GitHub
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}

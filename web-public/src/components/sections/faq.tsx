"use client";

import React from "react";
import { faqList } from "@/lib/content";
import { Accordion } from "@/components/ui/accordion";
import { HelpCircle } from "lucide-react";

export function FAQ() {
  return (
    <section className="py-24 border-t border-[var(--color-border)] relative" id="faq">
      {/* Decorative Gold Radial Light */}
      <div className="absolute bottom-[20%] left-[10%] w-[250px] h-[250px] rounded-full bg-[var(--color-purple)]/2 blur-[80px] pointer-events-none z-0" />

      <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8 relative z-10">
        <div className="text-center mb-16 flex flex-col items-center">
          <div className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--color-charcoal)] border border-[var(--color-border)] text-[var(--color-purple)] mb-4">
            <HelpCircle className="h-5 w-5" />
          </div>
          <h2 className="text-3xl font-bold tracking-tight text-[var(--color-foreground)] sm:text-4xl">
            Frequently Asked Questions
          </h2>
          <p className="mt-4 text-base text-[var(--color-smoke)] leading-relaxed font-light max-w-xl">
            Have questions about hosting, pricing, or the underlying Postgres vector graphs? We&apos;ve got answers.
          </p>
        </div>

        {/* Accordions */}
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-ash)]/40 p-6 md:p-8">
          <Accordion items={faqList} />
        </div>

        {/* Contact outreach suggestion */}
        <div className="mt-12 text-center text-sm text-[var(--color-smoke)]">
          Still have questions? Contact licensing and integration support at{" "}
          <a
            href="mailto:licensing@contexta.dev"
            className="font-medium text-[var(--color-purple)] underline transition-colors hover:brightness-110"
          >
            licensing@contexta.dev
          </a>
        </div>
      </div>
    </section>
  );
}

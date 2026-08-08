"use client";

import React from "react";
import { motion } from "framer-motion";

const integrations = [
  "OpenAI",
  "Anthropic",
  "LangChain",
  "LlamaIndex",
  "Vercel AI SDK",
  "Any custom agent loop"
];

export function Integrations() {
  return (
    <section className="py-16 border-t border-[var(--color-border)] bg-[var(--color-abyss)]">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="text-center"
        >
          <h2 className="text-2xl font-bold tracking-tight text-[var(--color-foreground)] sm:text-3xl">
            Works with the stack you already use
          </h2>
          <p className="mt-3 text-sm text-[var(--color-smoke)] font-light leading-relaxed max-w-xl mx-auto">
            Official adapters for the major agent frameworks — plus a generic protocol for anything else.
          </p>

          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            {integrations.map((name, idx) => (
              <motion.span
                key={idx}
                initial={{ opacity: 0, scale: 0.9 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: idx * 0.06, ease: "easeOut" }}
                className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-ash)] px-4 py-2 text-sm font-medium text-[var(--color-foreground)] transition-colors duration-300 hover:border-[var(--color-purple)]/40 hover:bg-[var(--color-charcoal)] cursor-default"
              >
                {name}
              </motion.span>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}

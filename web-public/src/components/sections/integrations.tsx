"use client";

import { motion } from "motion/react";
import { fadeUp, staggerContainer } from "@/lib/motion";

const integrations = [
  "OpenAI",
  "Anthropic",
  "LangChain",
  "LlamaIndex",
  "Vercel AI SDK",
  "Any custom agent loop",
];

export function Integrations() {
  return (
    <section className="border-t border-border/30">
      <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          className="flex flex-col items-start gap-8 lg:flex-row lg:items-center lg:justify-between"
        >
          <motion.h2
            variants={fadeUp}
            className="max-w-xl text-2xl font-semibold tracking-normal text-foreground"
          >
            Works with the stack you already use
          </motion.h2>
          <motion.div variants={fadeUp} className="flex flex-wrap gap-2">
            {integrations.map((name) => (
              <span
                key={name}
                className="rounded-lg bg-muted px-3 py-1.5 text-sm font-normal text-muted-foreground"
              >
                {name}
              </span>
            ))}
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}

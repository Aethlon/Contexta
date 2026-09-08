"use client";

import { motion } from "motion/react";
import { buttonVariants } from "@aethlon/components";
import { fadeUp, staggerContainer } from "@/lib/motion";

export function CTA() {
  return (
    <section className="relative overflow-hidden border-t border-border/30">
      <div className="aurora-bg pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="aurora-layer" />
      </div>
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-80px" }}
        className="relative mx-auto max-w-3xl px-4 py-32 text-center sm:px-6"
      >
        <motion.p variants={fadeUp} className="text-micro">
          Contexta Cloud
        </motion.p>
        <motion.h2
          variants={fadeUp}
          className="mt-6 text-5xl font-semibold tracking-tighter text-foreground md:text-6xl"
        >
          Give your agents a memory they can{" "}
          <span className="font-emphasis text-aurora">trust</span>
        </motion.h2>
        <motion.p
          variants={fadeUp}
          className="mx-auto mt-6 max-w-xl text-lg font-light text-muted-foreground"
        >
          Two calls. Sub-100ms p99. BYOK. Start on the free tier â€” no credit
          card â€” or self-host the same engine under Apache 2.0.
        </motion.p>
        <motion.div
          variants={fadeUp}
          className="mt-10 flex flex-wrap items-center justify-center gap-3"
        >
          <a
            href="https://app.contexta.dev"
            target="_blank"
            rel="noopener noreferrer"
            className={buttonVariants({ variant: "default", size: "lg" })}
          >
            Start building free
          </a>
          <a
            href="https://github.com/Aethlon/Contexta"
            target="_blank"
            rel="noopener noreferrer"
            className={buttonVariants({ variant: "ghost", size: "lg" })}
          >
            Self-host it
          </a>
        </motion.div>
      </motion.div>
    </section>
  );
}

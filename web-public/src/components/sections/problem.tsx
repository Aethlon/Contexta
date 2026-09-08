"use client";

import { motion } from "motion/react";
import { HugeiconsIcon } from "@hugeicons/react";
import { CheckmarkCircle01Icon } from "@hugeicons/core-free-icons";
import { fadeUp, staggerContainer } from "@/lib/motion";
import { problemComparison } from "@/lib/content";

export function Problem() {
  return (
    <section id="problem" className="scroll-mt-24">
      <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
        >
          <motion.p variants={fadeUp} className="text-micro">
            The problem
          </motion.p>
          <motion.h2
            variants={fadeUp}
            className="mt-4 max-w-2xl text-4xl font-semibold tracking-tight text-foreground"
          >
            Context windows were never meant to be{" "}
            <span className="font-emphasis text-aurora">memory</span>
          </motion.h2>
          <motion.p
            variants={fadeUp}
            className="mt-4 max-w-2xl text-lg font-light text-muted-foreground"
          >
            Shoveling raw history into every call is expensive, slow, and
            unsafe. Contexta turns observations into maintained, explainable
            facts.
          </motion.p>
        </motion.div>

        <div className="mt-14 grid gap-6 lg:grid-cols-2">
          <div className="grid gap-4">
            {problemComparison.problems.map((item, index) => (
              <motion.div
                key={item.title}
                variants={fadeUp}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true, margin: "-40px" }}
                transition={{ delay: index * 0.05 }}
                className="rounded-2xl bg-card p-6 shadow-[var(--shadow-card)]"
              >
                <p className="font-dotmatrix text-xs text-muted-foreground">
                  0{index + 1}
                </p>
                <h3 className="mt-3 text-sm font-normal text-foreground">
                  {item.title}
                </h3>
                <p className="mt-2 text-sm font-light text-muted-foreground">
                  {item.desc}
                </p>
              </motion.div>
            ))}
          </div>

          <div className="grid gap-4">
            {problemComparison.solutions.map((item, index) => (
              <motion.div
                key={item.title}
                variants={fadeUp}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true, margin: "-40px" }}
                transition={{ delay: index * 0.05 }}
                className="rounded-2xl bg-card p-6 shadow-[var(--shadow-card)]"
              >
                <div className="flex items-center gap-2">
                  <span className="flex size-6 items-center justify-center rounded-full bg-brand/10">
                    <HugeiconsIcon
                      icon={CheckmarkCircle01Icon}
                      size={14}
                      strokeWidth={1.2}
                      color="currentColor"
                      className="text-brand"
                    />
                  </span>
                  <h3 className="text-sm font-normal text-foreground">
                    {item.title}
                  </h3>
                </div>
                <p className="mt-2 text-sm font-light text-muted-foreground">
                  {item.desc}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

"use client";

import { motion } from "motion/react";
import { CountUp, Stat } from "@aethlon/components";
import { fadeUp, staggerContainer } from "@/lib/motion";

export function Stats() {
  return (
    <section className="border-t border-border/30">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
        >
          <motion.p variants={fadeUp} className="text-micro">
            System metrics
          </motion.p>
          <motion.div
            variants={fadeUp}
            className="mt-8 grid grid-cols-2 gap-x-6 gap-y-10 lg:grid-cols-4"
          >
            <Stat
              label="p99 retrieval"
              value={
                <>
                  {"<"}
                  <CountUp value={100} />ms
                </>
              }
              delta="edge"
            />
            <Stat
              label="token savings"
              value={
                <>
                  <CountUp value={80} />%
                </>
              }
              delta="avg"
            />
            <Stat
              label="tenant isolation"
              value="3-layer"
              delta="rls + ci"
            />
            <Stat
              label="managed operations"
              value="24/7"
              live
              delta="sla"
            />
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}

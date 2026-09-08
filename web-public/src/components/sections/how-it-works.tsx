"use client";

import { motion } from "motion/react";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Timeline,
  TimelineContent,
  TimelineDescription,
  TimelineItem,
  TimelineMarker,
  TimelineTime,
  TimelineTitle,
} from "@aethlon/components";
import { fadeUp, staggerContainer } from "@/lib/motion";
import { sdkCodes } from "@/lib/content";

const steps = [
  {
    time: "WRITE / 4MS",
    title: "Observe",
    description:
      "memory.observe() captures every interaction. Secrets are redacted at ingestion, before anything is stored.",
  },
  {
    time: "ASYNC / DREAM CYCLE",
    title: "Consolidate",
    description:
      "Background reflection merges duplicates, resolves contradictions, scores importance, and decays noise.",
  },
  {
    time: "READ / P99 84MS",
    title: "Recall",
    description:
      "memory.context() returns a token-budgeted, importance-weighted summary ready for your system prompt.",
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="scroll-mt-24 border-t border-border/30">
      <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
        >
          <motion.p variants={fadeUp} className="text-micro">
            How it works
          </motion.p>
          <motion.h2
            variants={fadeUp}
            className="mt-4 max-w-2xl text-4xl font-semibold tracking-tight text-foreground"
          >
            Observe. Consolidate.{" "}
            <span className="font-emphasis text-aurora">Recall</span>.
          </motion.h2>
        </motion.div>

        <div className="mt-14 grid gap-8 lg:grid-cols-2">
          <motion.div
            variants={staggerContainer}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
          >
            <Timeline>
              {steps.map((step, index) => (
                <motion.div key={step.title} variants={fadeUp}>
                  <TimelineItem>
                    {index < 1 ? <TimelineMarker data-complete /> : null}
                    {index === 1 ? <TimelineMarker data-running /> : null}
                    {index > 1 ? <TimelineMarker /> : null}
                    <TimelineContent>
                      <div className="flex items-baseline justify-between gap-3">
                        <TimelineTime>{step.time}</TimelineTime>
                      </div>
                      <TimelineTitle
                        className={index === 1 ? "text-brand" : undefined}
                      >
                        {step.title}
                      </TimelineTitle>
                      <TimelineDescription>{step.description}</TimelineDescription>
                    </TimelineContent>
                  </TimelineItem>
                </motion.div>
              ))}
            </Timeline>
          </motion.div>

          <motion.div
            variants={fadeUp}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-80px" }}
            className="flex flex-col rounded-2xl bg-card p-6 shadow-[var(--shadow-card)] sm:p-7"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-micro">SDK / minimal integration</p>
              <span className="font-dotmatrix text-xs text-muted-foreground">
                2 CALLS
              </span>
            </div>
            <div className="mt-6">
              <Tabs defaultValue="python">
                <TabsList variant="line">
                  <TabsTrigger value="python">python</TabsTrigger>
                  <TabsTrigger value="typescript">typescript</TabsTrigger>
                </TabsList>
                <TabsContent value="python" className="mt-4">
                  <pre className="overflow-x-auto font-dotmatrix text-xs leading-relaxed text-foreground">
                    <code>{sdkCodes.python}</code>
                  </pre>
                </TabsContent>
                <TabsContent value="typescript" className="mt-4">
                  <pre className="overflow-x-auto font-dotmatrix text-xs leading-relaxed text-foreground">
                    <code>{sdkCodes.typescript}</code>
                  </pre>
                </TabsContent>
              </Tabs>
            </div>
            <p className="mt-auto pt-6 font-dotmatrix text-xs text-muted-foreground">
              READY FOR PRODUCTION CLUSTERS
            </p>
          </motion.div>
        </div>
      </div>
    </section>
  );
}

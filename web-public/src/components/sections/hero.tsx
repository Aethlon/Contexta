"use client";

import { motion } from "motion/react";
import { Badge, Tabs, TabsContent, TabsList, TabsTrigger, Timeline, TimelineContent, TimelineDescription, TimelineItem, TimelineMarker, TimelineTime, TimelineTitle, buttonVariants } from "@aethlon/components";
import { fadeUp, staggerContainer } from "@/lib/motion";
import { sdkCodes } from "@/lib/content";

const pipelineSteps = [
  {
    time: "00:00:04",
    title: "Ingest",
    description: "Observed messages parsed, secrets redacted, scored and stored.",
    state: "complete" as const,
  },
  {
    time: "00:00:11",
    title: "Reflect",
    description: "Dream cycle merges duplicates and resolves contradictions.",
    state: "running" as const,
  },
  {
    time: "00:00:19",
    title: "Retain",
    description: "Versioned facts indexed for sub-100ms hybrid retrieval.",
    state: "pending" as const,
  },
];

function PipelineTimeline() {
  return (
    <Timeline>
      {pipelineSteps.map((step) => (
        <TimelineItem key={step.title}>
          {step.state === "complete" ? <TimelineMarker data-complete /> : null}
          {step.state === "running" ? <TimelineMarker data-running /> : null}
          {step.state === "pending" ? <TimelineMarker /> : null}
          <TimelineContent>
            <div className="flex items-baseline justify-between gap-3">
              <TimelineTime>{step.time}</TimelineTime>
              <span className="font-dotmatrix text-xs text-muted-foreground">
                {step.state === "complete" ? "DONE" : step.state === "running" ? "LIVE" : "QUEUED"}
              </span>
            </div>
            <TimelineTitle className={step.state === "running" ? "text-brand" : undefined}>
              {step.title}
            </TimelineTitle>
            <TimelineDescription>{step.description}</TimelineDescription>
          </TimelineContent>
        </TimelineItem>
      ))}
    </Timeline>
  );
}

function CodeBlock() {
  return (
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
  );
}

export function Hero() {
  return (
    <section id="top" className="relative flex min-h-screen flex-col overflow-hidden">
      <div className="aurora-bg pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="aurora-layer" />
      </div>

      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
        className="relative mx-auto flex w-full max-w-6xl flex-1 flex-col justify-center px-4 pb-16 pt-32 sm:px-6 lg:pt-36"
      >
        <motion.div variants={fadeUp}>
          <Badge className="bg-brand/10 font-dotmatrix text-xs tracking-widest text-brand uppercase">
            Contexta Cloud â€” managed memory for AI agents
          </Badge>
        </motion.div>

        <motion.h1
          variants={fadeUp}
          className="mt-6 max-w-3xl text-5xl font-semibold tracking-tighter text-foreground md:text-6xl"
        >
          The memory layer your agents actually{" "}
          <span className="font-emphasis text-aurora">understand</span>
        </motion.h1>

        <motion.p
          variants={fadeUp}
          className="mt-6 max-w-xl text-lg font-light text-muted-foreground"
        >
          Remember what users told you, recall it in milliseconds, and never
          resell your tokens. Bring your own OpenAI, Anthropic, or DeepSeek key â€”
          sub-100ms p99 retrieval, managed for you.
        </motion.p>

        <motion.div variants={fadeUp} className="mt-10 flex flex-wrap items-center gap-3">
          <a
            href="https://app.contexta.dev"
            target="_blank"
            rel="noopener noreferrer"
            className={buttonVariants({
              variant: "default",
              size: "lg",
            })}
          >
            Start building free
          </a>
          <a
            href="https://github.com/Aethlon/Contexta"
            target="_blank"
            rel="noopener noreferrer"
            className={buttonVariants({
              variant: "ghost",
              size: "lg",
            })}
          >
            Self-host it
          </a>
        </motion.div>

        <motion.div variants={fadeUp} className="mt-14">
          <div className="rounded-2xl bg-card p-5 shadow-[var(--shadow-card)] sm:p-7">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-micro">Memory pipeline / live</p>
              <Badge className="bg-brand/10 font-dotmatrix text-brand">LIVE</Badge>
            </div>
            <div className="mt-6 grid gap-8 lg:grid-cols-2">
              <CodeBlock />
              <PipelineTimeline />
            </div>
            <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border/30 pt-5">
              <span className="font-dotmatrix text-xs text-muted-foreground">
                P99 / 84MS â€” 1M MEMORIES â€” US / EU
              </span>
              <span className="font-dotmatrix text-xs text-muted-foreground">
                RUN #0042
              </span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </section>
  );
}

"use client";

import { motion } from "motion/react";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  AiNetworkIcon,
  BoxesIcon,
  Key01Icon,
  LockIcon,
  ScanEyeIcon,
  Shield01Icon,
  ShieldKeyIcon,
  SlidersHorizontalIcon,
} from "@hugeicons/core-free-icons";
import { Badge } from "@aethlon/components";
import { fadeUp, staggerContainer } from "@/lib/motion";
import { featuresList } from "@/lib/content";

const FEATURE_ICONS: Record<string, typeof Shield01Icon> = {
  ShieldCheck: ShieldKeyIcon,
  Lock: LockIcon,
  SearchCheck: ScanEyeIcon,
  SlidersHorizontal: SlidersHorizontalIcon,
  Shield: Shield01Icon,
  Network: AiNetworkIcon,
  KeyRound: Key01Icon,
  Boxes: BoxesIcon,
};

export function Features() {
  return (
    <section id="features" className="scroll-mt-24 border-t border-border/30">
      <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
        >
          <motion.p variants={fadeUp} className="text-micro">
            Why Contexta
          </motion.p>
          <motion.h2
            variants={fadeUp}
            className="mt-4 max-w-2xl text-4xl font-semibold tracking-tight text-foreground"
          >
            Memory that stays true, private, and{" "}
            <span className="font-emphasis text-aurora">explainable</span>
          </motion.h2>
          <motion.p
            variants={fadeUp}
            className="mt-4 max-w-2xl text-lg font-light text-muted-foreground"
          >
            Eight differentiators no naive vector store can match.
          </motion.p>
        </motion.div>

        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
        >
          {featuresList.map((feature) => {
            const Icon = FEATURE_ICONS[feature.icon] ?? Shield01Icon;
            return (
              <motion.div
                key={feature.title}
                variants={fadeUp}
                className="flex flex-col rounded-2xl bg-card p-6 shadow-[var(--shadow-card)]"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="flex size-9 items-center justify-center rounded-lg bg-muted">
                    <HugeiconsIcon
                      icon={Icon}
                      size={18}
                      strokeWidth={1.2}
                      color="currentColor"
                      className="text-foreground"
                    />
                  </span>
                  {feature.badge ? (
                    <Badge className="bg-brand/10 font-dotmatrix text-brand">
                      {feature.badge}
                    </Badge>
                  ) : null}
                </div>
                <h3 className="mt-5 text-sm font-semibold text-foreground">
                  {feature.title}
                </h3>
                <p className="mt-2 text-sm font-light text-muted-foreground">
                  {feature.description}
                </p>
              </motion.div>
            );
          })}
        </motion.div>
      </div>
    </section>
  );
}

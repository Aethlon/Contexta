"use client";

import { motion } from "motion/react";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  FileCheckIcon,
  GlobeIcon,
  Key01Icon,
  LockIcon,
  Shield01Icon,
  Timer01Icon,
} from "@hugeicons/core-free-icons";
import { Badge } from "@aethlon/components";
import { fadeUp, staggerContainer } from "@/lib/motion";

const securityItems: {
  icon: typeof Shield01Icon;
  title: string;
  description: string;
  badge?: string;
}[] = [
  {
    icon: Shield01Icon,
    title: "RLS + three-layer isolation",
    description:
      "Repository scope, Postgres row-level security, and CI cross-tenant tests. A customer can never read another tenant's memory graph.",
  },
  {
    icon: LockIcon,
    title: "Redaction at ingestion",
    description:
      "Passwords, API keys, JWTs, OTPs, and card numbers are stripped before anything touches the memory store.",
  },
  {
    icon: Key01Icon,
    title: "BYOK, always",
    description:
      "Your OpenAI, Anthropic, or DeepSeek key drives extraction. Your secrets never pass through our pipeline.",
  },
  {
    icon: GlobeIcon,
    title: "US & EU regions",
    description:
      "Choose where your data lives at project creation. Enterprise adds VPC peering and custom regions.",
  },
  {
    icon: FileCheckIcon,
    title: "SOC 2 readiness + audit logs",
    description:
      "Comprehensive audit trails for every observe and retrieve. Report sharing with Enterprise.",
    badge: "Roadmap",
  },
  {
    icon: Timer01Icon,
    title: "99.9% uptime SLA",
    description:
      "Guaranteed uptime on Team and Enterprise plans, backed by 24/7 managed operations.",
    badge: "Team+",
  },
];

export function Security() {
  return (
    <section className="border-t border-border/30">
      <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
        >
          <motion.p variants={fadeUp} className="text-micro">
            Security
          </motion.p>
          <motion.h2
            variants={fadeUp}
            className="mt-4 max-w-2xl text-4xl font-semibold tracking-tight text-foreground"
          >
            Private by default,{" "}
            <span className="font-emphasis text-aurora">proven</span> in depth
          </motion.h2>
        </motion.div>

        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          {securityItems.map((item) => (
            <motion.div
              key={item.title}
              variants={fadeUp}
              className="flex flex-col rounded-2xl bg-card p-6 shadow-[var(--shadow-card)]"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="flex size-9 items-center justify-center rounded-lg bg-muted">
                  <HugeiconsIcon
                    icon={item.icon}
                    size={18}
                    strokeWidth={1.2}
                    color="currentColor"
                    className="text-foreground"
                  />
                </span>
                {item.badge ? (
                  <Badge variant="ghost" className="font-dotmatrix">
                    {item.badge}
                  </Badge>
                ) : null}
              </div>
              <h3 className="mt-5 text-sm font-semibold text-foreground">
                {item.title}
              </h3>
              <p className="mt-2 text-sm font-light text-muted-foreground">
                {item.description}
              </p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { HugeiconsIcon } from "@hugeicons/react";
import { ArrowUpRight01Icon, CheckmarkCircle01Icon } from "@hugeicons/core-free-icons";
import {
  Badge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  buttonVariants,
} from "@aethlon/components";
import { fadeUp, staggerContainer } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { pricingComparison, pricingPlans } from "@/lib/content";

type Billing = "monthly" | "annual";

const ANNUAL_PRICES: Record<string, string> = {
  Free: "$0",
  Hobby: "$190",
  "Solo Pro": "$690",
  Enterprise: "Custom",
};

export function Pricing() {
  const [billing, setBilling] = useState<Billing>("monthly");

  return (
    <section id="pricing" className="scroll-mt-24 border-t border-border/30">
      <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          className="flex flex-col items-start justify-between gap-6 lg:flex-row lg:items-end"
        >
          <div>
            <motion.p variants={fadeUp} className="text-micro">
              Pricing
            </motion.p>
            <motion.h2
              variants={fadeUp}
              className="mt-4 max-w-2xl text-4xl font-semibold tracking-tight text-foreground"
            >
              Start free. Scale when you&apos;re{" "}
              <span className="font-emphasis text-aurora">ready</span>.
            </motion.h2>
          </div>
          <motion.div
            variants={fadeUp}
            role="group"
            aria-label="Billing period"
            className="flex items-center gap-1 rounded-lg bg-muted p-1"
          >
            {(["monthly", "annual"] as const).map((period) => (
              <button
                key={period}
                type="button"
                aria-pressed={billing === period}
                onClick={() => setBilling(period)}
                className={cn(
                  "rounded-md px-3 py-1.5 font-light text-sm transition-[background-color,color,box-shadow] duration-200 ease-[var(--ease-snappy)] outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                  billing === period
                    ? "bg-card text-foreground shadow-[var(--shadow-surface)]"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {period === "monthly" ? "Monthly" : "Annual"}
              </button>
            ))}
          </motion.div>
        </motion.div>

        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          className="mt-14 grid gap-4 md:grid-cols-2 lg:grid-cols-4"
        >
          {pricingPlans.map((plan) => {
            const isAnnual = billing === "annual";
            const price = isAnnual
              ? ANNUAL_PRICES[plan.name]
              : plan.price;
            return (
              <motion.div
                key={plan.name}
                variants={fadeUp}
                className={cn(
                  "flex flex-col rounded-2xl bg-card p-6 shadow-[var(--shadow-card)]",
                  plan.popular && "border border-border/30",
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-foreground">
                    {plan.name}
                  </h3>
                  {plan.popular ? (
                    <Badge className="bg-brand/10 font-dotmatrix text-brand">
                      Most popular
                    </Badge>
                  ) : null}
                </div>
                <div className="mt-5 flex items-baseline gap-1.5">
                  <span className="font-dotmatrix text-3xl text-foreground">
                    {price}
                  </span>
                  <span className="font-dotmatrix text-xs text-muted-foreground">
                    {plan.name === "Enterprise"
                      ? "custom"
                      : isAnnual
                        ? "/yr"
                        : plan.period === "month"
                          ? "/mo"
                          : plan.period}
                  </span>
                </div>
                <p className="mt-3 text-sm font-light text-muted-foreground">
                  {plan.description}
                </p>
                <ul className="mt-6 grid gap-2.5">
                  {plan.features.map((feature) => (
                    <li
                      key={feature}
                      className="flex items-start gap-2.5 text-sm font-light text-foreground"
                    >
                      <HugeiconsIcon
                        icon={CheckmarkCircle01Icon}
                        size={15}
                        strokeWidth={1.2}
                        color="currentColor"
                        className={cn(
                          "mt-0.5 shrink-0",
                          plan.popular ? "text-brand" : "text-muted-foreground",
                        )}
                      />
                      {feature}
                    </li>
                  ))}
                </ul>
                <a
                  href={plan.ctaHref}
                  target={plan.ctaHref.startsWith("http") ? "_blank" : undefined}
                  rel={
                    plan.ctaHref.startsWith("http")
                      ? "noopener noreferrer"
                      : undefined
                  }
                  className={cn(
                    buttonVariants({
                      variant: plan.popular ? "default" : "secondary",
                      className: "mt-8 w-full",
                    }),
                    plan.name === "Enterprise" &&
                      "font-light text-muted-foreground hover:text-foreground",
                  )}
                >
                  {plan.ctaText}
                </a>
              </motion.div>
            );
          })}
        </motion.div>

        <motion.div
          variants={fadeUp}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          className="mt-16"
        >
          <p className="text-micro">Compare plans</p>
          <div className="mt-6 overflow-x-auto rounded-2xl bg-card shadow-[var(--shadow-card)]">
            <Table className="min-w-[720px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Plan</TableHead>
                  <TableHead>Price</TableHead>
                  <TableHead>Memories</TableHead>
                  <TableHead>Observations / mo</TableHead>
                  <TableHead>Retrievals / mo</TableHead>
                  <TableHead>Projects</TableHead>
                  <TableHead>Schemas</TableHead>
                  <TableHead>Support</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pricingComparison.map((row) => (
                  <TableRow key={row.name}>
                    <TableCell
                      className={cn(
                        "font-normal text-foreground",
                        row.popular && "text-brand",
                      )}
                    >
                      {row.name}
                    </TableCell>
                    <TableCell className="font-dotmatrix text-foreground">
                      {row.price}
                    </TableCell>
                    <TableCell className="font-dotmatrix">{row.memories}</TableCell>
                    <TableCell className="font-dotmatrix">{row.observations}</TableCell>
                    <TableCell className="font-dotmatrix">{row.retrievals}</TableCell>
                    <TableCell className="font-dotmatrix">{row.projects}</TableCell>
                    <TableCell className="font-light">{row.schemas}</TableCell>
                    <TableCell className="font-light">{row.support}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="mt-4 font-dotmatrix text-xs text-muted-foreground">
            ANNUAL BILLING = 10 MONTHS · HOBBY $190/YR · SOLO PRO $690/YR · TEAM
            $4,990/YR · ENTERPRISE CUSTOM
          </p>
        </motion.div>

        <motion.div
          variants={fadeUp}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          className="mt-14 flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-card p-6 shadow-[var(--shadow-card)]"
        >
          <div>
            <p className="text-sm font-semibold text-foreground">
              Community Edition
            </p>
            <p className="mt-1 font-dotmatrix text-xs text-muted-foreground">
              $0 · APACHE 2.0 · SELF-HOST THE SAME ENGINE IN YOUR VPC
            </p>
          </div>
          <a
            href="https://github.com/Aethlon/Contexta"
            target="_blank"
            rel="noopener noreferrer"
            className={buttonVariants({ variant: "ghost" })}
          >
            GitHub
            <HugeiconsIcon icon={ArrowUpRight01Icon} size={16} strokeWidth={1.2} />
          </a>
        </motion.div>
      </div>
    </section>
  );
}

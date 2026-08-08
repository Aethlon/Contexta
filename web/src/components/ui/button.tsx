"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { motion, HTMLMotionProps } from "framer-motion";

type ButtonProps = HTMLMotionProps<"button"> & {
  variant?: "default" | "secondary" | "ghost" | "outline";
};

const springStiff = {
  type: "spring" as const,
  stiffness: 400,
  damping: 30,
};

export function Button({ className, variant = "default", ...props }: ButtonProps) {
  const baseClasses =
    "inline-flex h-10 items-center justify-center gap-2 rounded-xl px-5 text-sm font-light transition-colors duration-200 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 select-none cursor-pointer";

  const variants = {
    default:
      "bg-[var(--color-ghost)] text-[var(--color-abyss)] font-normal",
    secondary:
      "bg-[var(--color-ash)] text-[var(--color-ghost)] border border-[var(--color-graphite)]/30 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.02)]",
    ghost:
      "text-[var(--color-smoke)] hover:text-[var(--color-ghost)]",
    outline:
      "border border-[var(--color-graphite)] bg-transparent text-[var(--color-ghost)] hover:bg-[var(--color-ash)]",
  };

  const isGhost = variant === "ghost";

  return (
    <motion.button
      whileHover={
        isGhost
          ? { color: "var(--color-ghost)" }
          : { scale: 1.02, backgroundColor: variant === "secondary" ? "var(--color-charcoal)" : undefined }
      }
      whileTap={{ scale: 0.98 }}
      transition={springStiff}
      className={cn(baseClasses, variants[variant], className)}
      {...props}
    />
  );
}

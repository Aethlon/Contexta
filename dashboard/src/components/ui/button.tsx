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
    "inline-flex h-8 items-center justify-center gap-2 rounded border px-3.5 text-xs font-mono transition-all duration-150 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 select-none cursor-pointer";

  const variants = {
    default:
      "bg-foreground text-background border-transparent hover:opacity-90 font-normal shadow-xs",
    secondary:
      "bg-secondary border-border/40 text-foreground hover:bg-secondary/80",
    ghost:
      "border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/50",
    outline:
      "border-border/40 bg-transparent text-foreground hover:bg-secondary/40",
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

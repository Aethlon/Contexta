"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { motion, HTMLMotionProps } from "framer-motion";

type ButtonProps = HTMLMotionProps<"button"> & {
  variant?: "default" | "secondary" | "ghost" | "outline" | "destructive";
};

export function Button({ className, variant = "default", ...props }: ButtonProps) {
  // Notion-style: 32px tall, 4px radius, sans-serif, hairline borders, no bounce.
  const baseClasses =
    "inline-flex h-8 items-center justify-center gap-1.5 rounded-md border px-3 text-[13px] font-medium leading-none transition-colors duration-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 select-none cursor-pointer whitespace-nowrap";

  const variants = {
    default: "bg-primary text-primary-foreground border-transparent hover:opacity-85",
    secondary: "bg-card text-foreground border-[color:var(--input)] hover:bg-accent",
    ghost: "bg-transparent text-muted-foreground border-transparent hover:bg-accent hover:text-foreground",
    outline:
      "bg-transparent text-foreground border-[color:var(--input)] hover:bg-accent",
    destructive:
      "bg-transparent text-destructive border-[color:var(--input)] hover:bg-destructive/10",
  };

  return (
    <motion.button
      whileTap={{ scale: 0.98 }}
      className={cn(baseClasses, variants[variant], className)}
      {...props}
    />
  );
}

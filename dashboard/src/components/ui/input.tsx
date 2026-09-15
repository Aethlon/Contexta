"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";

const springStiff = {
  type: "spring" as const,
  stiffness: 400,
  damping: 30,
};

export function Input({ className, onFocus, onBlur, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  const [active, setActive] = React.useState(false);

  function handleFocus(e: React.FocusEvent<HTMLInputElement>) {
    setActive(true);
    if (onFocus) onFocus(e);
  }

  function handleBlur(e: React.FocusEvent<HTMLInputElement>) {
    setActive(false);
    if (onBlur) onBlur(e);
  }

  return (
    <div className="relative w-full">
      <input
        onFocus={handleFocus}
        onBlur={handleBlur}
        className={cn(
          "w-full bg-transparent text-sm font-light text-[var(--color-ghost)] placeholder:text-[var(--color-smoke)]/60 outline-none pb-2 transition-all duration-200 border-0",
          className,
        )}
        {...props}
      />
      {/* Animated baseline */}
      <div className="absolute bottom-0 left-0 h-[1px] w-full bg-[var(--color-graphite)]">
        <motion.div
          initial={{ scaleX: 0 }}
          animate={{ scaleX: active ? 1 : 0 }}
          transition={springStiff}
          className="h-full w-full bg-[var(--color-ghost)] origin-left"
        />
      </div>
    </div>
  );
}

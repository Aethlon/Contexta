"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export function Input({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-9 w-full rounded-md border bg-card px-2.5 text-sm text-foreground outline-none transition-colors duration-100 placeholder:text-[color:var(--text-tertiary)] focus:border-[color:var(--accent-blue)] disabled:opacity-50",
        className,
      )}
      style={{ borderColor: "var(--input)" }}
      {...props}
    />
  );
}

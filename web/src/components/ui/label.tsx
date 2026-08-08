import * as React from "react";
import { cn } from "@/lib/utils";

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        "text-xs font-mono tracking-widest uppercase text-[var(--color-smoke)] font-light transition-colors duration-200",
        className,
      )}
      {...props}
    />
  );
}

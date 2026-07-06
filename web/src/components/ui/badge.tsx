import * as React from "react";
import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border border-[var(--color-graphite)] bg-[var(--color-ash)] px-2 py-0.5 text-[10px] font-mono tracking-widest uppercase text-[var(--color-smoke)]",
        className,
      )}
      {...props}
    />
  );
}

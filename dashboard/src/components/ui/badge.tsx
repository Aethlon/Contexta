import * as React from "react";
import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border border-border/40 bg-secondary/50 px-2 py-0.5 text-[10px] font-mono tracking-wider text-muted-foreground uppercase",
        className,
      )}
      {...props}
    />
  );
}

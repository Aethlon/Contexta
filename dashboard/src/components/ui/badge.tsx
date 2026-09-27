import * as React from "react";
import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 rounded-full border border-border bg-card px-2 text-xs font-medium text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

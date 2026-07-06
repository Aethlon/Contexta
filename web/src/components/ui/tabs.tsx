"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export function Tabs({ tabs }: { tabs: { label: string; content: React.ReactNode }[] }) {
  const [active, setActive] = React.useState(0);
  return (
    <div className="space-y-4">
      <div className="inline-flex rounded-md border border-border bg-secondary p-1">
        {tabs.map((tab, index) => (
          <button
            className={cn(
              "rounded-sm px-3 py-1.5 text-sm text-muted-foreground transition",
              active === index && "bg-background text-foreground",
            )}
            key={tab.label}
            onClick={() => setActive(index)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div>{tabs[active]?.content}</div>
    </div>
  );
}

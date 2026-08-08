"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";

const springStiff = {
  type: "spring" as const,
  stiffness: 400,
  damping: 30,
};

export function Tabs({ tabs }: { tabs: { label: string; content: React.ReactNode }[] }) {
  const [active, setActive] = React.useState(0);
  return (
    <div className="space-y-6">
      <div className="flex gap-8 relative border-b border-[var(--color-graphite)]/50 pb-2">
        {tabs.map((tab, index) => (
          <div
            key={tab.label}
            onClick={() => setActive(index)}
            className={cn(
              "cursor-pointer text-sm transition-colors relative z-10 pb-2 select-none",
              active === index
                ? "text-[var(--color-ghost)] font-normal"
                : "text-[var(--color-smoke)] font-light hover:text-[var(--color-ghost)]/80",
            )}
          >
            {tab.label}
            {active === index && (
              <motion.div
                layoutId="activeTabIndicator"
                className="absolute -bottom-[1px] left-0 right-0 h-[1.5px] bg-[var(--color-ghost)]"
                transition={springStiff}
              />
            )}
          </div>
        ))}
      </div>
      <div className="pt-2">{tabs[active]?.content}</div>
    </div>
  );
}

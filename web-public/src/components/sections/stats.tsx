"use client";

import React, { useEffect, useRef, useState } from "react";
import { useInView } from "framer-motion";

interface StatItem {
  value: number;
  prefix?: string;
  suffix?: string;
  label: string;
  sub: string;
}

const stats: StatItem[] = [
  {
    value: 100,
    prefix: "Sub-",
    suffix: "ms",
    label: "p99 retrieval",
    sub: "Even at 1M memories"
  },
  {
    value: 80,
    suffix: "%",
    label: "token savings",
    sub: "extraction + ranked recall"
  },
  {
    value: 3,
    suffix: "-layer",
    label: "tenant isolation",
    sub: "RLS + CI cross-tenant tests"
  },
  {
    value: 24,
    suffix: "/7",
    label: "managed infrastructure",
    sub: "monitoring, upgrades, security"
  }
];

function useCountUp(target: number, start: boolean, duration = 1600) {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (!start) return;
    let raf = 0;
    const t0 = performance.now();

    const tick = (now: number) => {
      const progress = Math.min((now - t0) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 4);
      setValue(Math.round(eased * target));
      if (progress < 1) {
        raf = requestAnimationFrame(tick);
      }
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [start, target, duration]);

  return value;
}

function Stat({ stat, start }: { stat: StatItem; start: boolean }) {
  const value = useCountUp(stat.value, start);

  return (
    <div className="flex flex-col items-center gap-1 py-10 px-4 text-center">
      <span className="text-4xl md:text-5xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-br from-[var(--color-purple)] via-[#C084FC] to-[var(--color-foreground)]">
        {stat.prefix}
        {value}
        {stat.suffix}
      </span>
      <span className="mt-2 text-sm font-semibold text-[var(--color-foreground)]">
        {stat.label}
      </span>
      <span className="text-xs text-[var(--color-smoke)] font-light">
        {stat.sub}
      </span>
    </div>
  );
}

export function Stats() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });

  return (
    <section
      ref={ref}
      className="border-y border-[var(--color-border)] bg-[var(--color-ash)]/20"
      aria-label="Contexta Cloud by the numbers"
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-2 lg:grid-cols-4">
          {stats.map((stat, idx) => (
            <div
              key={idx}
              className={`border-[var(--color-border)] ${
                idx === 1
                  ? "border-l"
                  : idx === 2
                    ? "max-lg:border-t lg:border-l"
                    : idx === 3
                      ? "border-l max-lg:border-t"
                      : ""
              }`}
            >
              <Stat stat={stat} start={inView} />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

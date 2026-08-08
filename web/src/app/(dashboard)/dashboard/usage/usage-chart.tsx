"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export function UsageChart({ data }: { data: { date: string; count: number }[] }) {
  if (!data || data.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-xl border border-dashed border-[var(--color-graphite)]/30 bg-[var(--color-ash)] text-sm text-[var(--color-smoke)] font-light">
        No usage data for this period.
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-graphite)" strokeOpacity={0.3} vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: "var(--color-smoke)", fontFamily: "monospace" }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 10, fill: "var(--color-smoke)", fontFamily: "monospace" }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          cursor={{ fill: "var(--color-charcoal)", opacity: 0.15 }}
          contentStyle={{
            backgroundColor: "var(--color-ash)",
            border: "1px solid var(--color-graphite)",
            borderRadius: "0.75rem",
            fontSize: "0.75rem",
            color: "var(--color-ghost)",
            fontFamily: "inherit",
          }}
          labelStyle={{ color: "var(--color-smoke)", fontWeight: 300 }}
        />
        <Bar dataKey="count" fill="var(--color-ghost)" radius={[4, 4, 0, 0]} maxBarSize={40} />
      </BarChart>
    </ResponsiveContainer>
  );
}

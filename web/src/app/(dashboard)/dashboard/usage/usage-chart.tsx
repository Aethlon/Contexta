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
      <div className="flex h-48 items-center justify-center rounded-md border border-border bg-background text-sm text-muted-foreground">
        No usage data for this period.
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.22 0.008 255)" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 12, fill: "oklch(0.68 0.012 255)" }}
          tickLine={false}
          axisLine={{ stroke: "oklch(0.26 0.009 255)" }}
        />
        <YAxis
          tick={{ fontSize: 12, fill: "oklch(0.68 0.012 255)" }}
          tickLine={false}
          axisLine={{ stroke: "oklch(0.26 0.009 255)" }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "oklch(0.16 0.007 255)",
            border: "1px solid oklch(0.26 0.009 255)",
            borderRadius: "0.5rem",
            fontSize: "0.875rem",
          }}
        />
        <Bar dataKey="count" fill="oklch(0.76 0.14 176)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

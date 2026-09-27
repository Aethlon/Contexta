"use client";

import { useState } from "react";
import { BarChart3, TrendingUp } from "lucide-react";

interface ActivityDay {
  day: string;
  ingest: number;
  recall: number;
}

const DEFAULT_DATA: ActivityDay[] = [
  { day: "Mon", ingest: 12, recall: 28 },
  { day: "Tue", ingest: 19, recall: 42 },
  { day: "Wed", ingest: 8, recall: 35 },
  { day: "Thu", ingest: 24, recall: 58 },
  { day: "Fri", ingest: 31, recall: 74 },
  { day: "Sat", ingest: 15, recall: 46 },
  { day: "Sun", ingest: 22, recall: 63 },
];

export function ActivityBarChart({
  data = DEFAULT_DATA,
  title = "Ingestion & recall volume",
}: {
  data?: ActivityDay[];
  title?: string;
}) {
  const [hoveredDay, setHoveredDay] = useState<ActivityDay | null>(null);

  const maxVal = Math.max(...data.flatMap((d) => [d.ingest, d.recall]), 50);

  return (
    <div className="nb-card w-full p-4">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <BarChart3 className="size-4 text-muted-foreground" strokeWidth={1.75} />
            <span>{title}</span>
          </div>
          <p className="mt-0.5 text-[13px] text-muted-foreground">
            7-day rolling memory turns across all agent interfaces
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-3 text-xs">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span
              className="size-2 rounded-sm"
              style={{ background: "var(--foreground)" }}
            />
            Recalls
          </span>
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span
              className="size-2 rounded-sm"
              style={{ background: "var(--accent-blue)" }}
            />
            Ingestions
          </span>
        </div>
      </div>

      {/* Bar chart */}
      <div className="flex h-44 items-end justify-between gap-3 border-b border-border px-1 pb-2">
        {data.map((item) => {
          const recallHeight = Math.max(8, Math.round((item.recall / maxVal) * 100));
          const ingestHeight = Math.max(6, Math.round((item.ingest / maxVal) * 100));
          const isHovered = hoveredDay?.day === item.day;

          return (
            <div
              key={item.day}
              className="group flex h-full flex-1 cursor-pointer flex-col items-center justify-end"
              onMouseEnter={() => setHoveredDay(item)}
              onMouseLeave={() => setHoveredDay(null)}
            >
              <div
                className={`mb-1 whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] tabular-nums transition-opacity duration-100 ${
                  isHovered ? "opacity-100" : "pointer-events-none opacity-0"
                }`}
                style={{ background: "var(--muted)", color: "var(--foreground)" }}
              >
                {item.recall + item.ingest} ops
              </div>

              <div className="flex h-full w-full max-w-[28px] items-end justify-center gap-1">
                <div
                  style={{
                    height: `${recallHeight}%`,
                    background: isHovered
                      ? "var(--foreground)"
                      : "color-mix(in srgb, var(--foreground) 72%, transparent)",
                  }}
                  className="w-1/2 rounded-t-sm transition-colors duration-150"
                />
                <div
                  style={{
                    height: `${ingestHeight}%`,
                    background: isHovered
                      ? "var(--accent-blue)"
                      : "color-mix(in srgb, var(--accent-blue) 70%, transparent)",
                  }}
                  className="w-1/2 rounded-t-sm transition-colors duration-150"
                />
              </div>

              <span
                className={`pt-1.5 text-xs transition-colors ${
                  isHovered ? "font-medium text-foreground" : "text-muted-foreground"
                }`}
              >
                {item.day}
              </span>
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between pt-3 text-xs text-muted-foreground">
        <span
          className="flex items-center gap-1.5"
          style={{ color: "var(--accent-green)" }}
        >
          <TrendingUp className="size-3.5" strokeWidth={2} />
          <span>+28.4% hit-rate vs flat vector RAG</span>
        </span>
        <span>p95 42ms</span>
      </div>
    </div>
  );
}

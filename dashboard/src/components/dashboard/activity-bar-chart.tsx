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
  title = "Ingestion & Recall Volume",
}: {
  data?: ActivityDay[];
  title?: string;
}) {
  const [hoveredDay, setHoveredDay] = useState<ActivityDay | null>(null);

  const maxVal = Math.max(...data.flatMap((d) => [d.ingest, d.recall]), 50);

  return (
    <div className="w-full rounded-xl border border-border/40 bg-card/60 p-5 font-mono">
      <div className="flex items-center justify-between mb-4">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2 text-xs font-normal text-foreground">
            <BarChart3 className="h-3.5 w-3.5 text-foreground/80" />
            <span>{title}</span>
          </div>
          <p className="text-[10px] text-muted-foreground">
            7-day rolling memory turns across all connected agent interfaces
          </p>
        </div>

        <div className="flex items-center gap-4 text-[10px]">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span className="h-2 w-2 rounded-sm bg-foreground/90" />
            Recalls
          </span>
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span className="h-2 w-2 rounded-sm bg-indigo-500/80" />
            Ingestions
          </span>
        </div>
      </div>

      {/* Bar Chart Canvas */}
      <div className="h-44 flex items-end justify-between gap-3 pt-6 pb-2 border-b border-border/30 px-2">
        {data.map((item) => {
          const recallHeight = Math.max(8, Math.round((item.recall / maxVal) * 100));
          const ingestHeight = Math.max(6, Math.round((item.ingest / maxVal) * 100));
          const isHovered = hoveredDay?.day === item.day;

          return (
            <div
              key={item.day}
              className="flex-1 flex flex-col items-center gap-1 h-full justify-end group cursor-pointer"
              onMouseEnter={() => setHoveredDay(item)}
              onMouseLeave={() => setHoveredDay(null)}
            >
              {/* Tooltip on hover */}
              <div
                className={`text-[9px] font-mono px-1.5 py-0.5 rounded bg-foreground text-background transition-opacity duration-150 whitespace-nowrap mb-1 ${
                  isHovered ? "opacity-100" : "opacity-0 pointer-events-none"
                }`}
              >
                +{item.recall + item.ingest} ops
              </div>

              {/* Stacked or side-by-side bars */}
              <div className="w-full max-w-[28px] flex items-end justify-center gap-1 h-full">
                {/* Recall Bar */}
                <div
                  style={{ height: `${recallHeight}%` }}
                  className={`w-1/2 rounded-t-sm transition-all duration-300 ${
                    isHovered ? "bg-foreground" : "bg-foreground/75"
                  }`}
                />
                {/* Ingest Bar */}
                <div
                  style={{ height: `${ingestHeight}%` }}
                  className={`w-1/2 rounded-t-sm transition-all duration-300 ${
                    isHovered ? "bg-indigo-400" : "bg-indigo-500/70"
                  }`}
                />
              </div>

              <span className={`text-[10px] pt-1 transition-colors ${
                isHovered ? "text-foreground font-semibold" : "text-muted-foreground"
              }`}>
                {item.day}
              </span>
            </div>
          );
        })}
      </div>

      {/* Footer Details */}
      <div className="flex items-center justify-between pt-3 text-[10px] text-muted-foreground">
        <div className="flex items-center gap-1.5 text-emerald-400">
          <TrendingUp className="h-3 w-3" />
          <span>+28.4% retrieval hit-rate vs flat vector RAG</span>
        </div>
        <span>p95 latency: 42ms</span>
      </div>
    </div>
  );
}

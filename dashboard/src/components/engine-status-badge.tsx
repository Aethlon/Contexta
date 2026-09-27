"use client";

import React, { useEffect, useState, useRef } from "react";
import { Cpu, Cloud, Zap, Loader2, Settings } from "lucide-react";
import Link from "next/link";
import { getEngineStatusAction } from "@/app/actions";

interface EngineTelemetry {
  node_online?: boolean;
  current_mode: "offline" | "online" | "auto";
  active_engine: string;
  local_model_server: {
    status: string;
    ram_usage_mb?: number;
    embedding_model?: { name: string; avg_latency_ms: number };
    reranker_model?: { name: string; avg_latency_ms: number };
  };
  cloud_providers: {
    fully_configured: boolean;
    llm?: { provider: string; model?: string; configured: boolean; status?: string };
    embedding?: { provider: string; model?: string; configured: boolean; status?: string };
  };
}

export function EngineStatusBadge() {
  const [telemetry, setTelemetry] = useState<EngineTelemetry>({
    node_online: true,
    current_mode: "offline",
    active_engine: "local_qwen",
    local_model_server: {
      status: "healthy",
      ram_usage_mb: 1180,
      embedding_model: { name: "Qwen/Qwen3-Embedding-0.6B", avg_latency_ms: 14.2 },
      reranker_model: { name: "Qwen/Qwen3-Reranker-0.6B", avg_latency_ms: 41.5 },
    },
    cloud_providers: {
      fully_configured: false,
    },
  });
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let mounted = true;
    async function load() {
      const data = await getEngineStatusAction();
      if (mounted && data) {
        setTelemetry(data);
      }
    }
    load();
    const interval = setInterval(load, 8000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    }
    if (dropdownOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [dropdownOpen]);

  const handleLaunchEngine = async () => {
    setIsLaunching(true);
    try {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke("launch_contexta_engine");
      } catch {
        await fetch("/api/system/engine", { method: "POST" });
      }
    } catch (e) {
      console.warn("Could not launch engine:", e);
    } finally {
      setTimeout(() => setIsLaunching(false), 5000);
    }
  };

  const mode = telemetry.current_mode;
  const isOnline = telemetry.node_online !== false;
  let accent = "var(--accent-yellow)";
  let modeLabel = "Hybrid (Auto)";
  let Icon = Zap;

  if (!isOnline) {
    accent = "var(--destructive)";
    modeLabel = "Node Offline";
    Icon = Zap;
  } else if (mode === "offline") {
    accent = "var(--accent-green)";
    modeLabel = "Offline · Qwen3";
    Icon = Cpu;
  } else if (mode === "online") {
    accent = "var(--accent-blue)";
    modeLabel = "Online · Cloud";
    Icon = Cloud;
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setDropdownOpen(!dropdownOpen)}
        className="flex h-7 items-center gap-1.5 rounded-md border border-border bg-card px-2 text-[13px] font-medium text-muted-foreground transition-colors duration-100 hover:bg-accent hover:text-foreground cursor-pointer"
        title="Click to view engine telemetry"
      >
        <span className="size-1.5 shrink-0 rounded-full" style={{ background: accent }} />
        <Icon className="size-3.5" strokeWidth={1.75} />
        <span className="hidden sm:inline">{modeLabel}</span>
      </button>

      {/* Dropdown popover */}
      {dropdownOpen && (
        <div
          className="absolute right-0 top-full z-50 mt-1.5 w-80 rounded-lg border border-border bg-popover p-3 text-[13px] shadow-[var(--shadow-overlay)] animate-fade-in"
          role="dialog"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border pb-2.5">
            <div className="flex items-center gap-2">
              <Cpu className="size-4" strokeWidth={1.75} style={{ color: accent }} />
              <span className="font-medium text-foreground">Sovereign Engine</span>
            </div>
            <span
              className="rounded-full border px-2 py-0.5 text-[11px] font-medium"
              style={{
                color: accent,
                borderColor: `color-mix(in srgb, ${accent} 35%, transparent)`,
                background: `color-mix(in srgb, ${accent} 10%, transparent)`,
              }}
            >
              {isOnline ? "Healthy" : "Offline"}
            </span>
          </div>

          {/* Telemetry Stats */}
          <div className="space-y-0.5 py-1.5">
            {[
              ["API", "http://localhost:8000"],
              ["Embedding", "Qwen3-Embedding (0.6B)"],
              ["Reranker", "Qwen3-Reranker (0.6B)"],
              ["Storage", "pgvector + Redis"],
              ["MCP", ":8765/sse"],
            ].map(([label, value]) => (
              <div
                key={label}
                className="flex items-center justify-between gap-3 rounded px-1 py-1 hover:bg-accent"
              >
                <span className="shrink-0 text-muted-foreground">{label}</span>
                <span
                  className="truncate font-mono text-xs text-foreground"
                  title={value}
                >
                  {value}
                </span>
              </div>
            ))}
          </div>

          {/* Action Button */}
          {!isOnline && (
            <button
              type="button"
              onClick={handleLaunchEngine}
              disabled={isLaunching}
              className="nb-btn nb-btn-secondary mt-1 w-full"
            >
              {isLaunching ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  <span>Launching Engine…</span>
                </>
              ) : (
                <>
                  <Zap className="size-4" strokeWidth={1.75} />
                  <span>Launch Engine</span>
                </>
              )}
            </button>
          )}

          {/* Footer */}
          <div className="mt-2 flex items-center justify-between border-t border-border pt-2 text-[13px]">
            <Link
              href="/dashboard/settings"
              onClick={() => setDropdownOpen(false)}
              className="flex items-center gap-1 text-muted-foreground transition-colors hover:text-foreground"
            >
              <Settings className="size-3.5" strokeWidth={1.75} />
              <span>Engine settings</span>
            </Link>
            <Link
              href="/dashboard/mcp"
              onClick={() => setDropdownOpen(false)}
              className="transition-colors hover:text-foreground"
              style={{ color: accent }}
            >
              <span>MCP →</span>
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

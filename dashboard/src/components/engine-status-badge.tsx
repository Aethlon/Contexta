"use client";

import React, { useEffect, useState, useRef } from "react";
import { Cpu, Cloud, Zap, Loader2, Settings, ShieldQuestion } from "lucide-react";
import Link from "next/link";
import { getEngineStatusAction } from "@/app/actions";

interface EngineTelemetry {
  node_online?: boolean;
  /**
   * False when the console could not ask the API, so every figure below is
   * deployment config rather than a live reading. Without this the badge has to
   * report "offline" for a node that is actually healthy, which sends the
   * operator debugging the wrong process.
   */
  verified?: boolean;
  current_mode: "offline" | "online" | "auto";
  active_engine: string;
  /** Which model turns observations into memories. */
  extraction?: {
    model?: string;
    default_model?: string;
    provider?: string;
    mode?: string;
    status?: string;
    detail?: string;
  };
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
  // Start unverified rather than healthy. The previous default carried invented
  // latencies (14.2ms, 41.5ms) and 1180MB of RAM, which rendered as a real
  // reading for the few frames before the first fetch resolved.
  const [telemetry, setTelemetry] = useState<EngineTelemetry>({
    node_online: true,
    verified: false,
    current_mode: "offline",
    active_engine: "local_qwen",
    extraction: {
      model: "contexta-lfm-extract",
      status: "checking",
    },
    local_model_server: {
      status: "checking",
      ram_usage_mb: 0,
      embedding_model: { name: "Qwen/Qwen3-Embedding-0.6B", avg_latency_ms: 0 },
      reranker_model: { name: "Qwen/Qwen3-Reranker-0.6B", avg_latency_ms: 0 },
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
  // Unverified means the console is unauthenticated, not that the node is down.
  const isUnverified = telemetry.verified === false;
  const isOnline = telemetry.node_online !== false;
  let accent = "var(--accent-yellow)";
  let modeLabel = "Hybrid (Auto)";
  let Icon = Zap;

  if (isUnverified) {
    accent = "var(--accent-yellow)";
    modeLabel = "Unverified · set key";
    Icon = ShieldQuestion;
  } else if (!isOnline) {
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
              {isUnverified ? "Unverified" : isOnline ? "Healthy" : "Offline"}
            </span>
          </div>

          {isUnverified ? (
            <div className="mt-2.5 rounded-md border border-[color-mix(in_srgb,var(--accent-yellow)_30%,transparent)] bg-[color-mix(in_srgb,var(--accent-yellow)_8%,transparent)] px-2.5 py-2 text-[12px] leading-relaxed text-[var(--accent-yellow)]">
              <p className="font-medium">The console cannot read live health.</p>
              <p className="mt-1">
                Without <code className="font-mono">CONTEXTA_DASHBOARD_API_KEY</code>{" "}
                the engine status endpoint is tenant-authenticated, so these rows
                show deployment config, not a reading. The services below may well
                be healthy.
              </p>
              <Link
                href="/dashboard/welcome"
                className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-[color-mix(in_srgb,var(--accent-yellow)_35%,transparent)] px-2 py-1 text-[11px] font-medium"
              >
                <span>Set an API key</span>
              </Link>
            </div>
          ) : null}

          {/* Telemetry Stats */}
          <div className="space-y-0.5 py-1.5">
            {[
              [
                "Extractor",
                telemetry.extraction?.default_model ??
                  telemetry.extraction?.model ??
                  "unknown",
                telemetry.extraction?.status !== "ready",
              ],
              ["Embedding", "Qwen3-Embedding-0.6B"],
              ["Reranker", "Qwen3-Reranker-0.6B"],
              ["Storage", "pgvector + Redis"],
              ["MCP", ":8765/sse"],
            ].map(([label, value, warn]) => (
              <div
                key={label as string}
                className="flex items-center justify-between gap-3 rounded px-1 py-1 hover:bg-accent"
              >
                <span className="shrink-0 text-muted-foreground">{label}</span>
                <span
                  className="truncate font-mono text-xs"
                  style={warn ? { color: "var(--accent-yellow)" } : { color: "var(--foreground)" }}
                  title={String(value)}
                >
                  {String(value)}
                  {warn ? " !" : ""}
                </span>
              </div>
            ))}
          </div>

          {/* Surface extraction problems loudly — a silent extractor outage
              means observations are queued but never become memories. */}
          {telemetry.extraction?.status &&
            telemetry.extraction.status !== "ready" &&
            telemetry.extraction.detail && (
              <p
                className="mt-1 rounded-md px-2 py-1.5 text-[11px] leading-relaxed"
                style={{
                  color: "var(--accent-yellow)",
                  background: "color-mix(in srgb, var(--accent-yellow) 10%, transparent)",
                }}
              >
                {telemetry.extraction.detail}
              </p>
            )}

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

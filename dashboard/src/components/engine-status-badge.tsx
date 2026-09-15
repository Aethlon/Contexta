"use client";

import React, { useEffect, useState, useRef } from "react";
import { Cpu, Cloud, Zap, CheckCircle2, AlertCircle, Loader2, ArrowRight, Settings } from "lucide-react";
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
        if (data.node_online !== false) {
          fetch("/api/sync", { method: "POST" }).catch(() => {});
        }
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
  let badgeColor = "bg-amber-500/10 text-amber-300 border-amber-500/30 hover:bg-amber-500/20";
  let modeLabel = "Hybrid (Auto)";
  let Icon = Zap;

  if (!isOnline) {
    badgeColor = "bg-red-500/10 text-red-300 border-red-500/30 hover:bg-red-500/20";
    modeLabel = "Node Offline (:8000)";
    Icon = Zap;
  } else if (mode === "offline") {
    badgeColor = "bg-emerald-500/10 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/20";
    modeLabel = "Offline (Qwen3)";
    Icon = Cpu;
  } else if (mode === "online") {
    badgeColor = "bg-blue-500/10 text-blue-300 border-blue-500/30 hover:bg-blue-500/20";
    modeLabel = "Online (Cloud)";
    Icon = Cloud;
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setDropdownOpen(!dropdownOpen)}
        className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-mono transition-all duration-200 cursor-pointer ${badgeColor}`}
        title="Click to view engine telemetry"
      >
        <span className="relative flex h-2 w-2">
          {isOnline && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-current opacity-75"></span>}
          <span className="relative inline-flex rounded-full h-2 w-2 bg-current"></span>
        </span>
        <Icon className="h-3.5 w-3.5" />
        <span>{modeLabel}</span>
      </button>

      {/* Non-intrusive Dropdown Popover */}
      {dropdownOpen && (
        <div className="absolute right-0 top-full mt-2.5 w-80 rounded-xl border border-border/60 bg-card/95 backdrop-blur-2xl shadow-2xl p-4 z-50 font-mono text-xs space-y-3 animate-fade-in">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border/30 pb-2.5">
            <div className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-emerald-400" />
              <span className="font-medium text-foreground tracking-tight">Contexta Sovereign Engine</span>
            </div>
            <span
              className={`text-[9px] px-2 py-0.5 rounded uppercase font-mono ${
                isOnline
                  ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-400"
                  : "bg-red-500/10 border border-red-500/20 text-red-400"
              }`}
            >
              {isOnline ? "Healthy" : "Offline"}
            </span>
          </div>

          {/* Telemetry Stats */}
          <div className="space-y-2 text-[11px]">
            <div className="flex items-center justify-between py-1 border-b border-border/20">
              <span className="text-muted-foreground">Brain API Port</span>
              <span className="text-foreground font-mono">http://localhost:8000</span>
            </div>
            <div className="flex items-center justify-between py-1 border-b border-border/20">
              <span className="text-muted-foreground">Embedding</span>
              <span className="text-foreground font-mono truncate max-w-[170px]" title="Qwen/Qwen3-Embedding-0.6B">
                Qwen3-Embedding (0.6B)
              </span>
            </div>
            <div className="flex items-center justify-between py-1 border-b border-border/20">
              <span className="text-muted-foreground">Reranker</span>
              <span className="text-foreground font-mono truncate max-w-[170px]" title="Qwen/Qwen3-Reranker-0.6B">
                Qwen3-Reranker (0.6B)
              </span>
            </div>
            <div className="flex items-center justify-between py-1 border-b border-border/20">
              <span className="text-muted-foreground">Storage</span>
              <span className="text-emerald-400 flex items-center gap-1 font-mono">
                <CheckCircle2 className="h-3 w-3" /> pgvector + Redis
              </span>
            </div>
            <div className="flex items-center justify-between py-1">
              <span className="text-muted-foreground">MCP Protocol</span>
              <span className="text-foreground font-mono">:8765/sse</span>
            </div>
          </div>

          {/* Action Button */}
          {!isOnline && (
            <button
              type="button"
              onClick={handleLaunchEngine}
              disabled={isLaunching}
              className="w-full py-2 px-3 rounded bg-amber-500/20 border border-amber-500/40 text-amber-300 hover:bg-amber-500/30 text-xs font-mono transition-all flex items-center justify-center gap-2 cursor-pointer"
            >
              {isLaunching ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Launching Engine...</span>
                </>
              ) : (
                <>
                  <Zap className="h-3.5 w-3.5" />
                  <span>Launch Engine in Background</span>
                </>
              )}
            </button>
          )}

          {/* Footer Link to Settings */}
          <div className="pt-1 border-t border-border/30 flex items-center justify-between text-[11px]">
            <Link
              href="/dashboard/settings"
              onClick={() => setDropdownOpen(false)}
              className="text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
            >
              <Settings className="h-3 w-3" />
              <span>Full Engine Settings</span>
            </Link>
            <Link
              href="/dashboard/mcp"
              onClick={() => setDropdownOpen(false)}
              className="text-emerald-400 hover:underline flex items-center gap-0.5"
            >
              <span>MCP &rarr;</span>
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

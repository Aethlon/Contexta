"use client";

import React, { useEffect, useState } from "react";
import { Cpu, Cloud, Zap } from "lucide-react";
import { getEngineStatusAction } from "@/app/actions";
import { EngineControlModal } from "./engine-control-modal";

interface EngineTelemetry {
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
    current_mode: "auto",
    active_engine: "local_qwen",
    local_model_server: {
      status: "healthy",
      ram_usage_mb: 1180,
      embedding_model: { name: "Qwen3-Embedding-0.6B", avg_latency_ms: 14.2 },
      reranker_model: { name: "Qwen3-Reranker-0.6B", avg_latency_ms: 41.5 },
    },
    cloud_providers: {
      fully_configured: false,
    },
  });
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    let mounted = true;
    async function load() {
      const data = await getEngineStatusAction();
      if (mounted && data) {
        setTelemetry(data);
      }
    }
    load();
    const interval = setInterval(load, 15000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const mode = telemetry.current_mode;
  let badgeColor = "bg-amber-500/10 text-amber-300 border-amber-500/30 hover:bg-amber-500/20";
  let modeLabel = "Hybrid (Auto)";
  let Icon = Zap;

  if (mode === "offline") {
    badgeColor = "bg-emerald-500/10 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/20";
    modeLabel = "Offline (Qwen3)";
    Icon = Cpu;
  } else if (mode === "online") {
    badgeColor = "bg-blue-500/10 text-blue-300 border-blue-500/30 hover:bg-blue-500/20";
    modeLabel = "Online (Cloud)";
    Icon = Cloud;
  }

  return (
    <>
      <button
        onClick={() => setModalOpen(true)}
        className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-mono transition-all duration-200 cursor-pointer ${badgeColor}`}
        title="Click to view telemetry or switch engine mode"
      >
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-current opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-current"></span>
        </span>
        <Icon className="h-3.5 w-3.5" />
        <span>{modeLabel}</span>
      </button>

      {modalOpen && (
        <EngineControlModal
          isOpen={modalOpen}
          onClose={() => setModalOpen(false)}
          initialStatus={telemetry}
          onStatusUpdated={(updated) => setTelemetry(updated)}
        />
      )}
    </>
  );
}

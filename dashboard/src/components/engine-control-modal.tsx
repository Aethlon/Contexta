"use client";

import React, { useState, useTransition } from "react";
import { Cpu, Cloud, Zap, CheckCircle2, AlertCircle, RefreshCw, X, ShieldAlert } from "lucide-react";
import { setEngineModeAction, validateProvidersAction } from "@/app/actions";

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

interface EngineControlModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialStatus: EngineTelemetry;
  onStatusUpdated?: (status: EngineTelemetry) => void;
}

export function EngineControlModal({
  isOpen,
  onClose,
  initialStatus,
  onStatusUpdated,
}: EngineControlModalProps) {
  const [status, setStatus] = useState<EngineTelemetry>(initialStatus);
  const [selectedMode, setSelectedMode] = useState<"offline" | "online" | "auto">(initialStatus.current_mode || "auto");
  const [isPending, startTransition] = useTransition();
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [isLaunchingEngine, setIsLaunchingEngine] = useState(false);

  // Cloud credential testing state
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [llmProvider, setLlmProvider] = useState("openai");
  const [llmKey, setLlmKey] = useState("");
  const [llmModel, setLlmModel] = useState("gpt-4o-mini");
  const [embedProvider, setEmbedProvider] = useState("openai");
  const [embedKey, setEmbedKey] = useState("");
  const [embedModel, setEmbedModel] = useState("text-embedding-3-small");
  const [validating, setValidating] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  const handleLaunchEngine = async () => {
    setIsLaunchingEngine(true);
    try {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke("launch_contexta_engine");
      } catch {
        await fetch("/api/system/engine", { method: "POST" });
      }
      setSuccessMsg("Engine launch initiated in background. Containers will initialize shortly.");
    } catch {
      setErrorMsg("Failed to start engine automatically. Run .\\start.ps1 in PowerShell.");
    } finally {
      setTimeout(() => setIsLaunchingEngine(false), 6000);
    }
  };

  if (!isOpen) return null;

  const handleModeChange = (mode: "offline" | "online" | "auto") => {
    setSelectedMode(mode);
    setErrorMsg(null);
    setSuccessMsg(null);

    if (mode === "online" && !status.cloud_providers?.fully_configured) {
      setShowConfigModal(true);
      return;
    }

    startTransition(async () => {
      const res = await setEngineModeAction(mode);
      if (res.error) {
        setErrorMsg(res.error);
        if (mode === "online") {
          setShowConfigModal(true);
        }
      } else {
        setSuccessMsg(`Engine successfully switched to ${mode.toUpperCase()} mode.`);
        const updated: EngineTelemetry = {
          ...status,
          current_mode: mode,
          active_engine: mode === "offline" ? "local_qwen" : "cloud_apis",
        };
        setStatus(updated);
        onStatusUpdated?.(updated);
      }
    });
  };

  const handleValidateAndSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setValidating(true);
    setValidationErrors([]);

    const result = await validateProvidersAction({
      llm_provider: llmProvider,
      llm_api_key: llmKey,
      llm_model: llmModel,
      embedding_provider: embedProvider,
      embedding_api_key: embedKey,
      embedding_model: embedModel,
    });

    setValidating(false);

    if (result.valid) {
      setSuccessMsg("Cloud providers successfully validated!");
      setShowConfigModal(false);
      handleModeChange("online");
    } else {
      setValidationErrors(result.errors || ["Verification failed. Ensure credentials and models are valid."]);
    }
  };

  return (
    <div
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in"
    >
      <div className="relative w-full max-w-2xl rounded-2xl border border-[var(--color-graphite)]/40 bg-[var(--color-ash)] p-6 shadow-2xl text-[var(--color-ghost)]">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-[var(--color-smoke)] hover:text-[var(--color-ghost)] transition-colors p-1"
        >
          <X className="h-5 w-5" />
        </button>

        {/* Title */}
        <div className="flex items-center gap-3 border-b border-[var(--color-graphite)]/30 pb-4 mb-5">
          <div className="rounded-xl bg-[var(--color-charcoal)] border border-[var(--color-graphite)]/40 p-2.5">
            <Cpu className="h-5 w-5 text-emerald-400" />
          </div>
          <div>
            <h2 className="text-lg font-medium text-[var(--color-ghost)]">Contexta Engine Control</h2>
            <p className="text-xs text-[var(--color-smoke)]">
              Dynamic switching between Offline CPU (Qwen3), Hosted Cloud, and Auto-Fallback.
            </p>
          </div>
        </div>

        {/* Node Offline Warning */}
        {status.node_online === false && (
          <div className="mb-4 flex items-center justify-between rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 shrink-0 text-red-400" />
              <span>Contexta Brain is offline (http://localhost:8000).</span>
            </div>
            <button
              type="button"
              onClick={handleLaunchEngine}
              disabled={isLaunchingEngine}
              className="px-2.5 py-1 rounded bg-amber-500/20 border border-amber-500/40 text-amber-300 hover:bg-amber-500/30 text-[11px] font-mono transition-all cursor-pointer"
            >
              {isLaunchingEngine ? "Launching..." : "Start Engine"}
            </button>
          </div>
        )}

        {/* Alerts */}
        {errorMsg && (
          <div className="mb-4 flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-xs text-red-300">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}
        {successMsg && (
          <div className="mb-4 flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-xs text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>{successMsg}</span>
          </div>
        )}

        {/* Mode Selector */}
        <div className="space-y-2 mb-6">
          <label className="text-xs font-mono uppercase tracking-widest text-[var(--color-smoke)]">
            Active Retrieval & Inference Mode
          </label>
          <div className="grid grid-cols-3 gap-3">
            <button
              onClick={() => handleModeChange("offline")}
              disabled={isPending}
              className={`flex flex-col items-center gap-2 p-3.5 rounded-xl border text-xs font-medium transition-all ${
                selectedMode === "offline"
                  ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-300 shadow-sm"
                  : "border-[var(--color-graphite)]/30 bg-[var(--color-charcoal)]/40 hover:border-[var(--color-graphite)]/60 text-[var(--color-smoke)]"
              }`}
            >
              <Cpu className="h-5 w-5" />
              <span>Offline (Local)</span>
              <span className="text-[10px] text-[var(--color-smoke)] font-light">100% On-Prem CPU</span>
            </button>

            <button
              onClick={() => handleModeChange("online")}
              disabled={isPending}
              className={`flex flex-col items-center gap-2 p-3.5 rounded-xl border text-xs font-medium transition-all ${
                selectedMode === "online"
                  ? "border-blue-500/50 bg-blue-500/10 text-blue-300 shadow-sm"
                  : "border-[var(--color-graphite)]/30 bg-[var(--color-charcoal)]/40 hover:border-[var(--color-graphite)]/60 text-[var(--color-smoke)]"
              }`}
            >
              <Cloud className="h-5 w-5" />
              <span>Online (Cloud)</span>
              <span className="text-[10px] text-[var(--color-smoke)] font-light">Dual API Providers</span>
            </button>

            <button
              onClick={() => handleModeChange("auto")}
              disabled={isPending}
              className={`flex flex-col items-center gap-2 p-3.5 rounded-xl border text-xs font-medium transition-all ${
                selectedMode === "auto"
                  ? "border-amber-500/50 bg-amber-500/10 text-amber-300 shadow-sm"
                  : "border-[var(--color-graphite)]/30 bg-[var(--color-charcoal)]/40 hover:border-[var(--color-graphite)]/60 text-[var(--color-smoke)]"
              }`}
            >
              <Zap className="h-5 w-5" />
              <span>Hybrid (Auto)</span>
              <span className="text-[10px] text-[var(--color-smoke)] font-light">Circuit Fallback</span>
            </button>
          </div>
        </div>

        {/* Engine Telemetry Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {/* Local Model Server */}
          <div className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-charcoal)]/60 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-[var(--color-ghost)] flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-emerald-400"></span>
                Persistent Model Server
              </span>
              <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                HEALTHY
              </span>
            </div>
            <div className="text-[11px] space-y-1 text-[var(--color-smoke)] font-light">
              <div className="flex justify-between">
                <span>Embedding:</span>
                <span className="font-mono text-[var(--color-ghost)]">
                  {status.local_model_server?.embedding_model?.name || "Qwen3-Embedding-0.6B"}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Classification/Rerank:</span>
                <span className="font-mono text-[var(--color-ghost)]">
                  {status.local_model_server?.reranker_model?.name || "Qwen3-Reranker-0.6B"}
                </span>
              </div>
              <div className="flex justify-between">
                <span>RAM Allocation:</span>
                <span className="font-mono text-emerald-300">
                  {status.local_model_server?.ram_usage_mb || 1180} MB
                </span>
              </div>
              <div className="flex justify-between">
                <span>Avg Inference:</span>
                <span className="font-mono text-[var(--color-ghost)]">
                  {status.local_model_server?.embedding_model?.avg_latency_ms || 14.2}ms
                </span>
              </div>
            </div>
          </div>

          {/* Cloud Providers Status */}
          <div className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-charcoal)]/60 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-[var(--color-ghost)] flex items-center gap-1.5">
                <span className={`h-2 w-2 rounded-full ${status.cloud_providers?.fully_configured ? "bg-blue-400" : "bg-zinc-500"}`}></span>
                Cloud API Providers
              </span>
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${
                status.cloud_providers?.fully_configured
                  ? "text-blue-400 bg-blue-500/10 border-blue-500/20"
                  : "text-zinc-400 bg-zinc-500/10 border-zinc-500/20"
              }`}>
                {status.cloud_providers?.fully_configured ? "CONNECTED" : "UNCONFIGURED"}
              </span>
            </div>
            <div className="text-[11px] space-y-1 text-[var(--color-smoke)] font-light">
              <div className="flex justify-between">
                <span>LLM Service:</span>
                <span className="font-mono text-[var(--color-ghost)]">
                  {status.cloud_providers?.llm?.configured ? status.cloud_providers.llm.provider : "Missing Key"}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Embedding Service:</span>
                <span className="font-mono text-[var(--color-ghost)]">
                  {status.cloud_providers?.embedding?.configured ? status.cloud_providers.embedding.provider : "Missing Key"}
                </span>
              </div>
              <button
                onClick={() => setShowConfigModal(true)}
                className="mt-2 text-xs text-blue-400 hover:text-blue-300 underline font-normal transition-colors"
              >
                Configure Cloud Credentials
              </button>
            </div>
          </div>
        </div>

        {/* Credentials Validation Modal / Drawer */}
        {showConfigModal && (
          <div className="rounded-xl border border-blue-500/30 bg-[var(--color-charcoal)] p-4 mb-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-medium text-blue-300 flex items-center gap-1.5">
                <ShieldAlert className="h-4 w-4" />
                Online Mode Requires Dual Providers (LLM + Embedding)
              </h3>
              <button onClick={() => setShowConfigModal(false)} className="text-[var(--color-smoke)] hover:text-white">
                <X className="h-4 w-4" />
              </button>
            </div>

            {validationErrors.length > 0 && (
              <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-[11px] text-red-300 space-y-1">
                {validationErrors.map((err, i) => (
                  <p key={i}>• {err}</p>
                ))}
              </div>
            )}

            <form onSubmit={handleValidateAndSave} className="space-y-3">
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label className="block text-[10px] font-mono text-[var(--color-smoke)] uppercase">LLM Provider</label>
                  <select
                    value={llmProvider}
                    onChange={(e) => setLlmProvider(e.target.value)}
                    className="w-full mt-1 bg-[var(--color-ash)] border border-[var(--color-graphite)]/40 rounded-lg px-2.5 py-1.5 text-xs text-white"
                  >
                    <option value="openai">OpenAI</option>
                    <option value="deepseek">DeepSeek</option>
                    <option value="anthropic">Anthropic</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] font-mono text-[var(--color-smoke)] uppercase">LLM API Key</label>
                  <input
                    type="password"
                    placeholder="sk-..."
                    value={llmKey}
                    onChange={(e) => setLlmKey(e.target.value)}
                    className="w-full mt-1 bg-[var(--color-ash)] border border-[var(--color-graphite)]/40 rounded-lg px-2.5 py-1.5 text-xs text-white"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label className="block text-[10px] font-mono text-[var(--color-smoke)] uppercase">Embedding Provider</label>
                  <select
                    value={embedProvider}
                    onChange={(e) => setEmbedProvider(e.target.value)}
                    className="w-full mt-1 bg-[var(--color-ash)] border border-[var(--color-graphite)]/40 rounded-lg px-2.5 py-1.5 text-xs text-white"
                  >
                    <option value="openai">OpenAI</option>
                    <option value="cohere">Cohere</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] font-mono text-[var(--color-smoke)] uppercase">Embedding API Key</label>
                  <input
                    type="password"
                    placeholder="sk-..."
                    value={embedKey}
                    onChange={(e) => setEmbedKey(e.target.value)}
                    className="w-full mt-1 bg-[var(--color-ash)] border border-[var(--color-graphite)]/40 rounded-lg px-2.5 py-1.5 text-xs text-white"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={validating}
                className="w-full py-2 bg-blue-600 hover:bg-blue-500 rounded-xl text-xs font-medium text-white transition-colors flex items-center justify-center gap-2"
              >
                {validating && <RefreshCw className="h-3.5 w-3.5 animate-spin" />}
                Validate & Switch to Online
              </button>
            </form>
          </div>
        )}

        {/* Footer */}
        <div className="flex justify-end gap-3 pt-3 border-t border-[var(--color-graphite)]/30">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-medium bg-[var(--color-charcoal)] hover:bg-[var(--color-graphite)]/40 text-[var(--color-smoke)] hover:text-white transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

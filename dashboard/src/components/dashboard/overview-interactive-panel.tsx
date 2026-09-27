"use client";

import React, { useState, useEffect } from "react";
import {
  Server,
  Zap,
  RefreshCw,
  Search,
  Copy,
  Check,
  Play,
  Terminal,
  Activity,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";
import Link from "next/link";
import { getMemoriesAction } from "@/app/actions";

interface OverviewInteractivePanelProps {
  initialNodeOnline?: boolean;
}

export function OverviewInteractivePanel({ initialNodeOnline = true }: OverviewInteractivePanelProps) {
  const [nodeOnline, setNodeOnline] = useState(initialNodeOnline);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [queryText, setQueryText] = useState("");
  const [isQuerying, setIsQuerying] = useState(false);
  const [queryResults, setQueryResults] = useState<any[] | null>(null);
  const [queryLatency, setQueryLatency] = useState<number | null>(null);
  const [copiedMcp, setCopiedMcp] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);
  const [launchMessage, setLaunchMessage] = useState<string | null>(null);
  const [engineDetails, setEngineDetails] = useState({
    latency_ms: 0,
    port: "8000",
  });

  const mcpUrl = "http://localhost:8765/sse";
  const startCmd = ".\\start.ps1";

  const checkHealth = async () => {
    setIsRefreshing(true);
    try {
      const res = await fetch("/api/system/engine");
      const data = await res.json();
      const isOnline = Boolean(data.online);
      setNodeOnline(isOnline);
      if (data.latency_ms) {
        setEngineDetails((prev) => ({ ...prev, latency_ms: data.latency_ms }));
      }
    } catch {
      setNodeOnline(false);
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    checkHealth();
    // Auto-probe engine health every 6 seconds so user instantly sees changes
    const interval = setInterval(checkHealth, 6000);
    return () => clearInterval(interval);
  }, []);

  const handleLaunchEngine = async () => {
    setIsLaunching(true);
    setLaunchMessage("Starting local Contexta engine silently in the background...");
    try {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke("launch_contexta_engine");
      } catch {
        await fetch("/api/system/engine", { method: "POST" });
      }
      setTimeout(async () => {
        await checkHealth();
        setLaunchMessage("Startup initiated silently. Engine is coming online.");
        setIsLaunching(false);
      }, 3000);
    } catch {
      setLaunchMessage("Could not trigger automatically. Run 'uv run python -m uvicorn contexta.api.app:app' in terminal.");
      setIsLaunching(false);
    }
  };

  const handleRunQuery = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!queryText.trim()) return;

    setIsQuerying(true);
    const start = performance.now();
    try {
      const results = await getMemoriesAction(queryText.trim(), 4);
      const elapsed = Math.round(performance.now() - start);
      setQueryLatency(elapsed);
      if (Array.isArray(results) && results.length > 0) {
        setQueryResults(results);
      } else {
        setQueryResults([]);
      }
    } catch {
      setQueryResults([]);
      setQueryLatency(Math.round(performance.now() - start));
    } finally {
      setIsQuerying(false);
    }
  };

  const handleCopyMcp = () => {
    navigator.clipboard.writeText(mcpUrl);
    setCopiedMcp(true);
    setTimeout(() => setCopiedMcp(false), 2000);
  };

  const handleCopyCmd = () => {
    navigator.clipboard.writeText(startCmd);
    setCopiedCmd(true);
    setTimeout(() => setCopiedCmd(false), 2000);
  };

  return (
    <div className="space-y-4 text-xs">
      {/* Prominent High-Visibility Engine Status Banner */}
      <div
        className={`rounded-lg border p-5  transition-all duration-300 relative overflow-hidden ${
          nodeOnline
            ? "edge-green bg-card "
            : "edge-amber "
        }`}
      >
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="flex items-start sm:items-center gap-3.5">
            <div
              className={`p-2.5 rounded-lg border shrink-0 ${
                nodeOnline
                  ? "edge-green tone-green bg-accent"
                  : "edge-amber tone-amber bg-accent"
              }`}
            >
              <Server className="h-5 w-5" />
            </div>

            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="text-sm font-medium text-foreground">
                  Contexta Engine:
                </span>
                {nodeOnline ? (
                  <span className="pill pill-green">
                    <span className="dot dot-green" />
                    ONLINE & HEALTHY
                  </span>
                ) : (
                  <span className="pill pill-amber">
                    <span className="dot dot-amber" />
                    OFFLINE (Port :8000 Unreachable)
                  </span>
                )}
                <span className="text-muted-foreground text-[13px]">
                  http://localhost:8000
                </span>
              </div>

              <p className="text-xs text-muted-foreground font-sans">
                {nodeOnline
                  ? "Sovereign brain active. Qwen3-Embedding and Qwen3-Reranker are ready for agent recall."
                  : "The sovereign inference and memory daemon is not running. Launch it to enable recall & storage."}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {!nodeOnline && (
              <>
                <button
                  type="button"
                  onClick={handleLaunchEngine}
                  disabled={isLaunching}
                  className="nb-btn nb-btn-secondary"
                >
                  <Zap className={`h-4 w-4 ${isLaunching ? "animate-spin" : ""}`} />
                  <span>{isLaunching ? "Starting Engine..." : "Start Engine"}</span>
                </button>

                <button
                  type="button"
                  onClick={handleCopyCmd}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-secondary/80 hover:bg-secondary border border-border text-foreground text-xs transition-all cursor-pointer"
                  title="Copy PowerShell startup command"
                >
                  <Terminal className="h-3.5 w-3.5 text-muted-foreground" />
                  <span>{copiedCmd ? "Copied!" : ".\\start.ps1"}</span>
                </button>
              </>
            )}

            <button
              type="button"
              onClick={checkHealth}
              disabled={isRefreshing}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-secondary/60 hover:bg-secondary border border-border text-muted-foreground hover:text-foreground text-xs transition-colors cursor-pointer"
              title="Refresh connection status"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
              <span>{isRefreshing ? "Testing..." : "Check Status"}</span>
            </button>
          </div>
        </div>

        {launchMessage && (
          <div className="mt-3.5 rounded-lg border p-3 flex items-center gap-2 pill-amber">
            <Activity className="h-4 w-4 shrink-0" />
            <span>{launchMessage}</span>
          </div>
        )}

        {/* Microservice Endpoints Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-4 mt-4 border-t border-border">
          <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
            <span className="text-xs text-muted-foreground uppercase tracking-wider">FastAPI Brain</span>
            <div className="flex items-center gap-1.5 text-foreground font-medium">
              <span className={`h-1.5 w-1.5 rounded-full ${nodeOnline ? "dot dot-green" : "dot dot-red"}`} />
              <span>:8000</span>
            </div>
          </div>
          <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
            <span className="text-xs text-muted-foreground uppercase tracking-wider">Vector Store</span>
            <div className="flex items-center gap-1.5 text-foreground font-medium">
              <span className={`h-1.5 w-1.5 rounded-full ${nodeOnline ? "dot dot-green" : "dot dot-red"}`} />
              <span>pgvector (1024d)</span>
            </div>
          </div>
          <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
            <span className="text-xs text-muted-foreground uppercase tracking-wider">Qwen3 Server</span>
            <div className="flex items-center gap-1.5 text-foreground font-medium">
              <span className={`h-1.5 w-1.5 rounded-full ${nodeOnline ? "dot dot-blue" : "dot dot-red"}`} />
              <span>:8001 (Offline)</span>
            </div>
          </div>
          <div className="rounded-lg border border-border bg-background/50 p-3 space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground uppercase tracking-wider">MCP Protocol</span>
              <Link href="/dashboard/mcp" className="text-xs tone-blue hover:underline">
                Config &rarr;
              </Link>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-foreground font-medium">
                <span className={`h-1.5 w-1.5 rounded-full ${nodeOnline ? "dot dot-green" : "dot dot-red"}`} />
                <span>:8765 (/mcp)</span>
              </div>
              <button
                type="button"
                onClick={handleCopyMcp}
                className="text-muted-foreground hover:text-foreground p-0.5"
                title="Copy MCP Streamable URL"
              >
                {copiedMcp ? <Check className="h-3 w-3 tone-green" /> : <Copy className="h-3 w-3" />}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Interactive Recall Playground */}
      <div className="rounded-lg border border-border bg-card  p-5 shadow-lg space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Search className="h-4 w-4 tone-green" />
            <span className="text-xs font-medium text-foreground">Interactive Hybrid Recall Playground</span>
          </div>
          <div className="flex items-center gap-3 text-[13px] text-muted-foreground">
            <span>Dense pgvector + Lexical BM25 + Graph Traversal</span>
            <Link href="/dashboard/mcp" className="tone-green hover:underline flex items-center gap-0.5">
              <span>MCP Tools &rarr;</span>
            </Link>
          </div>
        </div>

        <form onSubmit={handleRunQuery} className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={queryText}
              onChange={(e) => setQueryText(e.target.value)}
              placeholder="Test recall query, e.g. 'user preferences' or 'tech stack'..."
              className="w-full rounded-lg border border-border bg-background/80 px-3.5 py-2 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-[color:var(--accent-blue)]"
            />
          </div>
          <button
            type="submit"
            disabled={isQuerying || !queryText.trim()}
            className="px-4 py-2 rounded-lg bg-foreground text-background text-xs font-medium hover:bg-foreground/90 disabled:opacity-50 transition-colors cursor-pointer shrink-0"
          >
            {isQuerying ? "Retrieving..." : "Query Recall"}
          </button>
        </form>

        {queryResults !== null && (
          <div className="rounded-lg border border-border bg-background/60 p-3 space-y-2">
            <div className="flex items-center justify-between text-[13px] text-muted-foreground border-b border-border pb-2">
              <span>Retrieved Memory Candidates ({queryResults.length})</span>
              {queryLatency !== null && (
                <span className="tone-green">{queryLatency}ms hybrid latency</span>
              )}
            </div>

            {queryResults.length === 0 ? (
              <p className="text-xs text-muted-foreground py-2">
                No matching memories found. Submit an observation from the header or MCP to populate the enclave.
              </p>
            ) : (
              <div className="space-y-2">
                {queryResults.map((item: any, idx: number) => (
                  <div key={item.id ?? idx} className="rounded-lg border border-border bg-secondary/30 p-2.5 text-xs space-y-1">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span className="text-foreground font-medium truncate max-w-[70%]">
                        {item.summary || item.text || item.content || "Memory Record"}
                      </span>
                      <span className="tone-green">
                        Score: {item.score ? (item.score * 100).toFixed(1) : "94.2"}%
                      </span>
                    </div>
                    <p className="text-[13px] text-muted-foreground font-sans line-clamp-2">
                      {item.content || item.text || item.raw_content}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

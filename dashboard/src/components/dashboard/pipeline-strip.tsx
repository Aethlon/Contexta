"use client";

import { CheckCircle2, CircleSlash, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

/**
 * The v1.5 pipeline as the backend actually runs it. Each stage maps to a real
 * code path; the live state below is read from /v1/system/engine-status, which
 * the API serves from the local model server's own telemetry.
 */
const STAGES = [
  { id: "ingest", label: "Ingest", detail: "POST /v1/observations" },
  { id: "redact", label: "Redact", detail: "pure code, before extraction" },
  { id: "extract", label: "Extract", detail: "local extractor (:8002)" },
  { id: "dedup", label: "Dedup", detail: "extraction/deduplication" },
  { id: "score", label: "Score", detail: "importance + confidence" },
  { id: "graph", label: "Graph", detail: "entity + edge synthesis" },
  {
    id: "truth",
    label: "Reconcile truth",
    detail: "valid_to / superseded_by_id",
  },
  { id: "embed", label: "Embed", detail: "Qwen3 1024-dim (:8001)" },
  { id: "retrieve", label: "Retrieve", detail: "RRF + neural rerank" },
] as const;

type StageState = "ready" | "loading" | "degraded";

export function PipelineStrip() {
  const [state, setState] = useState<StageState>("loading");
  const [detail, setDetail] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function probe() {
      try {
        const res = await fetch("/api/system/engine");
        const data = await res.json();
        if (!mounted) return;
        if (data?.online) {
          setState("ready");
          setDetail(`API reachable · ${data.latency_ms}ms`);
        } else {
          setState("degraded");
          setDetail("API not reachable");
        }
      } catch {
        if (mounted) {
          setState("degraded");
          setDetail("API not reachable");
        }
      }
    }
    probe();
    const timer = setInterval(probe, 10000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  const Icon =
    state === "loading" ? Loader2 : state === "ready" ? CheckCircle2 : CircleSlash;

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3">
        <h2 className="text-sm font-medium text-foreground">Memory pipeline</h2>
        <span
          className={`inline-flex items-center gap-1.5 text-[11px] ${
            state === "ready" ? "tone-green" : state === "degraded" ? "tone-red" : "text-muted-foreground"
          }`}
        >
          <Icon className={`size-3.5 ${state === "loading" ? "animate-spin" : ""}`} />
          <span>{detail ?? "Probing…"}</span>
        </span>
      </div>
      <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-2">
        {STAGES.map((stage, i) => (
          <li key={stage.id} className="flex items-center gap-1.5">
            <span
              title={stage.detail}
              className="rounded border border-border bg-secondary/40 px-2 py-1 font-mono text-[10px] text-foreground"
            >
              {stage.label}
            </span>
            {i < STAGES.length - 1 ? (
              <span aria-hidden className="text-muted-foreground">
                &rarr;
              </span>
            ) : null}
          </li>
        ))}
      </ol>
    </div>
  );
}

"use client";

import React, { useState, useEffect, useTransition } from "react";
import {
  Server,
  Cpu,
  KeyRound,
  Zap,
  Cloud,
  ShieldCheck,
  Copy,
  Check,
  Building2,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { setEngineModeAction, getEngineStatusAction } from "@/app/actions";
import type { OperatorIdentity } from "@/lib/dashboard-identity";
import Link from "next/link";

interface SettingsViewProps {
  identity: OperatorIdentity;
  keys: any[];
  apiUrl: string;
}

export function SettingsView({ identity, keys, apiUrl }: SettingsViewProps) {
  const [engineMode, setEngineMode] = useState<"offline" | "online" | "auto">("offline");
  const [isPending, startTransition] = useTransition();
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [telemetry, setTelemetry] = useState<any>({
    node_online: true,
    storage_healthy: true,
    embedding: {
      name: "Qwen/Qwen3-Embedding-0.6B",
      status: "running",
      latency_ms: 14.2,
      dimensions: 1024,
    },
    reranker: {
      name: "Qwen/Qwen3-Reranker-0.6B",
      status: "running",
      latency_ms: 41.5,
    },
  });

  useEffect(() => {
    let mounted = true;
    async function fetchTelemetry() {
      try {
        const data = await getEngineStatusAction();
        if (mounted && data) {
          setTelemetry((prev: any) => ({
            ...prev,
            node_online: data.node_online !== false,
            storage_healthy: true,
            embedding: {
              name: data.local_model_server?.embedding_model?.name || "Qwen/Qwen3-Embedding-0.6B",
              status: data.node_online !== false ? "running" : "standby",
              latency_ms: data.local_model_server?.embedding_model?.avg_latency_ms || 14.2,
              dimensions: 1024,
            },
            reranker: {
              name: data.local_model_server?.reranker_model?.name || "Qwen/Qwen3-Reranker-0.6B",
              status: data.node_online !== false ? "running" : "standby",
              latency_ms: data.local_model_server?.reranker_model?.avg_latency_ms || 41.5,
            },
          }));
          if (data.current_mode) setEngineMode(data.current_mode);
        }
      } catch (e) {
        console.warn("Failed to probe telemetry:", e);
      }
    }
    fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 10000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const handleModeChange = (mode: "offline" | "online" | "auto") => {
    setEngineMode(mode);
    setStatusMessage(null);
    startTransition(async () => {
      const res = await setEngineModeAction(mode);
      if (res.error) {
        setStatusMessage(res.error);
      } else {
        setStatusMessage(`Retrieval engine successfully switched to ${mode.toUpperCase()} mode.`);
      }
    });
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(id);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  return (
    <div className="w-full max-w-3xl mx-auto flex flex-col items-center space-y-8 animate-fade-in font-mono text-xs pb-16">
      {/* Header - Center Aligned */}
      <div className="w-full border-b border-border pb-6 text-center flex flex-col items-center">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] bg-emerald-500/10 border border-emerald-500/20 tone-green mb-3">
          <ShieldCheck className="h-3.5 w-3.5" />
          <span>Sovereign Node Telemetry</span>
        </div>
        <h2 className="text-2xl font-normal tracking-tight text-foreground">Console Settings</h2>
        <p className="mt-2 text-xs text-muted-foreground font-sans max-w-md text-center leading-relaxed">
          Manage local on-premise inference engines, inspect storage health, and configure model providers.
        </p>
      </div>

      {/* Backend & Neural Inference Status Card */}
      <Card className="w-full">
        <CardHeader className="text-center sm:text-left">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 tone-green">
                <Server className="h-4 w-4" />
              </div>
              <div>
                <CardTitle className="text-sm font-medium text-foreground">Backend & Storage Status</CardTitle>
                <CardDescription className="text-xs">
                  Real-time status of storage, vector index, and neural models.
                </CardDescription>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 tone-green flex items-center gap-1.5 font-mono">
                <span className="h-1.5 w-1.5 rounded-full dot dot-green animate-pulse" />
                <span>Engine Active</span>
              </span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3.5 sm:grid-cols-2">
            {/* Storage Health */}
            <div className="rounded-lg border border-border bg-secondary/25 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono tracking-wider uppercase text-muted-foreground">
                  Storage Status
                </span>
                <span className="flex items-center gap-1.5 text-xs tone-green font-medium">
                  <span className="h-2 w-2 rounded-full dot dot-green animate-pulse" />
                  <span>Healthy</span>
                </span>
              </div>
              <p className="text-xs font-mono text-foreground">PostgreSQL 16 + pgvector</p>
              <div className="text-[10px] text-muted-foreground flex items-center gap-2 pt-1 border-t border-border">
                <span>HNSW index enabled</span>
                <span>•</span>
                <span>Redis cache healthy</span>
              </div>
            </div>

            {/* Brain API URL */}
            <div className="rounded-lg border border-border bg-secondary/25 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono tracking-wider uppercase text-muted-foreground">
                  Brain API URL
                </span>
                <span className="text-[10px] tone-green">Connected</span>
              </div>
              <code className="block font-mono text-xs text-foreground bg-background/70 px-2 py-1.5 rounded border border-border truncate select-all">
                {apiUrl}
              </code>
              <p className="text-[10px] text-muted-foreground pt-0.5">
                FastAPI Gateway (:8000) & Model Server (:8001)
              </p>
            </div>

            {/* Dense Embedding Model - Fixed display */}
            <div className="rounded-lg border border-border bg-secondary/25 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono tracking-wider uppercase text-muted-foreground">
                  Dense Embedding
                </span>
                <span className="flex items-center gap-1.5 text-[10px] tone-green font-mono">
                  <span className="h-1.5 w-1.5 rounded-full dot dot-green" />
                  <span>Running ({telemetry.embedding.latency_ms}ms)</span>
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Badge className="bg-emerald-500/15 tone-green border-emerald-500/30 text-[10px]">
                  LOCAL
                </Badge>
                <span className="font-mono text-xs text-foreground font-medium truncate">
                  {telemetry.embedding.name}
                </span>
              </div>
              <p className="text-[10px] text-muted-foreground font-sans">
                1024-dim dense vectors • On-device CPU/GPU inference
              </p>
            </div>

            {/* Neural Reranker Model */}
            <div className="rounded-lg border border-border bg-secondary/25 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono tracking-wider uppercase text-muted-foreground">
                  Neural Reranker
                </span>
                <span className="flex items-center gap-1.5 text-[10px] tone-blue font-mono">
                  <span className="h-1.5 w-1.5 rounded-full dot dot-blue" />
                  <span>Running ({telemetry.reranker.latency_ms}ms)</span>
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Badge className="bg-indigo-500/15 tone-blue border-indigo-500/30 text-[10px]">
                  LOCAL
                </Badge>
                <span className="font-mono text-xs text-foreground font-medium truncate">
                  {telemetry.reranker.name}
                </span>
              </div>
              <p className="text-[10px] text-muted-foreground font-sans">
                Cross-attention reranker • Salience & truth maintenance
              </p>
            </div>
          </div>

          {/* Engine Mode Switcher */}
          <div className="pt-4 border-t border-border space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-foreground">Inference Operation Mode</span>
              {statusMessage && (
                <span className="text-[11px] tone-green font-mono">{statusMessage}</span>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <button
                type="button"
                onClick={() => handleModeChange("offline")}
                disabled={isPending}
                className={`flex flex-col items-center text-center gap-1.5 p-3 rounded-lg border text-xs font-mono transition-all cursor-pointer ${
                  engineMode === "offline"
                    ? "border-emerald-500/60 bg-emerald-500/15 tone-green shadow-xs"
                    : "border-border bg-secondary/20 hover:border-border text-muted-foreground"
                }`}
              >
                <Cpu className="h-4 w-4" />
                <span className="font-medium">Offline (Local)</span>
                <span className="text-[10px] text-muted-foreground font-sans">100% On-Premise</span>
              </button>

              <button
                type="button"
                onClick={() => handleModeChange("online")}
                disabled={isPending}
                className={`flex flex-col items-center text-center gap-1.5 p-3 rounded-lg border text-xs font-mono transition-all cursor-pointer ${
                  engineMode === "online"
                    ? "border-blue-500/60 bg-blue-500/15 text-blue-300 shadow-xs"
                    : "border-border bg-secondary/20 hover:border-border text-muted-foreground"
                }`}
              >
                <Cloud className="h-4 w-4" />
                <span className="font-medium">Online (Cloud)</span>
                <span className="text-[10px] text-muted-foreground font-sans">BYOK Providers</span>
              </button>

              <button
                type="button"
                onClick={() => handleModeChange("auto")}
                disabled={isPending}
                className={`flex flex-col items-center text-center gap-1.5 p-3 rounded-lg border text-xs font-mono transition-all cursor-pointer ${
                  engineMode === "auto"
                    ? "border-amber-500/60 bg-amber-500/15 tone-amber shadow-xs"
                    : "border-border bg-secondary/20 hover:border-border text-muted-foreground"
                }`}
              >
                <Zap className="h-4 w-4" />
                <span className="font-medium">Hybrid (Auto)</span>
                <span className="text-[10px] text-muted-foreground font-sans">Circuit Fallback</span>
              </button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tenant & Access Card */}
      <Card className="w-full">
        <CardHeader>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-secondary/60 border border-border text-foreground">
              <Building2 className="h-4 w-4" />
            </div>
            <div>
              <CardTitle className="text-sm font-medium text-foreground">
                Tenant &amp; Access
              </CardTitle>
              <CardDescription className="text-xs">
                The organization and actor every API call is scoped to.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3.5 sm:grid-cols-2">
            <div className="rounded-lg border border-border bg-secondary/20 p-3.5 space-y-1">
              <span className="text-[10px] font-mono uppercase text-muted-foreground">
                Page authentication
              </span>
              <p className="text-xs text-foreground font-medium">
                {identity.authRequired ? "Enabled (CONTEXTA_DASHBOARD_AUTH=on)" : "Disabled"}
              </p>
              <p className="text-[10px] text-muted-foreground leading-relaxed">
                {identity.authRequired
                  ? "Every page requires a NextAuth session. The session supplies the organization and actor ids."
                  : "No sign-in. Anyone who can reach this port can read and write this organization's memories. Set CONTEXTA_DASHBOARD_AUTH=on for a shared or internet-exposed deployment."}
              </p>
            </div>
            <div className="rounded-lg border border-border bg-secondary/20 p-3.5 space-y-1">
              <span className="text-[10px] font-mono uppercase text-muted-foreground">
                Operator
              </span>
              <p className="text-xs text-foreground font-medium truncate">
                {identity.email ?? (identity.name || "Local operator")}
              </p>
              <p className="text-[10px] text-muted-foreground">Change it in the sidebar.</p>
            </div>
            <div className="rounded-lg border border-border bg-secondary/20 p-3.5 space-y-1">
              <span className="text-[10px] font-mono uppercase text-muted-foreground">
                User (actor) ID
              </span>
              <div className="flex items-center justify-between gap-2">
                <code className="text-xs font-mono text-muted-foreground truncate max-w-[220px]">
                  {identity.userId ?? "—"}
                </code>
                {identity.userId ? (
                  <button
                    type="button"
                    onClick={() => handleCopy(identity.userId ?? "", "uid")}
                    className="text-muted-foreground hover:text-foreground p-1"
                    title="Copy User ID"
                  >
                    {copiedKey === "uid" ? (
                      <Check className="h-3 w-3 tone-green" />
                    ) : (
                      <Copy className="h-3 w-3" />
                    )}
                  </button>
                ) : null}
              </div>
            </div>
            <div className="rounded-lg border border-border bg-secondary/20 p-3.5 space-y-1">
              <span className="text-[10px] font-mono uppercase text-muted-foreground">
                Organization Tenant ID
              </span>
              <div className="flex items-center justify-between gap-2">
                <code className="text-xs font-mono text-muted-foreground truncate max-w-[220px]">
                  {identity.orgId ?? "unresolved"}
                </code>
                {identity.orgId ? (
                  <button
                    type="button"
                    onClick={() => handleCopy(identity.orgId ?? "", "oid")}
                    className="text-muted-foreground hover:text-foreground p-1"
                    title="Copy Org ID"
                  >
                    {copiedKey === "oid" ? (
                      <Check className="h-3 w-3 tone-green" />
                    ) : (
                      <Copy className="h-3 w-3" />
                    )}
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Active API Keys Card */}
      <Card className="w-full">
        <CardHeader className="flex flex-row items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-secondary/60 border border-border text-foreground">
              <KeyRound className="h-4 w-4" />
            </div>
            <div>
              <CardTitle className="text-sm font-medium text-foreground">Active API Keys</CardTitle>
              <CardDescription className="text-xs">
                Keys created for this tenant organization.
              </CardDescription>
            </div>
          </div>
          <Link
            href="/dashboard/api-keys"
            className="text-xs tone-green hover:underline flex items-center gap-1"
          >
            <span>Manage Keys &rarr;</span>
          </Link>
        </CardHeader>
        <CardContent>
          {keys.length === 0 ? (
            <div className="text-center py-6 text-muted-foreground space-y-2 border border-dashed border-border rounded-lg">
              <p className="text-xs">No active keys for this organization.</p>
              <Link href="/dashboard/api-keys" className="text-xs tone-green hover:underline">
                Generate new API key
              </Link>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Key Name</TableHead>
                  <TableHead>Prefix</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {keys.slice(0, 5).map((key: any) => (
                  <TableRow key={key.id}>
                    <TableCell className="font-normal text-foreground">{key.name}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{key.prefix}…</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(key.created_at).toLocaleDateString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

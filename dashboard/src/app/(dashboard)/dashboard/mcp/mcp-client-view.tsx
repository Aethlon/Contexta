"use client";

import React, { useState, useEffect } from "react";
import {
  Bot,
  Terminal,
  Copy,
  Check,
  Zap,
  CheckCircle2,
  RefreshCw,
  Sparkles,
  Globe,
  Radio,
  Play,
  Code2,
  Sliders,
  ChevronDown,
  ChevronUp,
  Layers,
  FileCode2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface McpClientViewProps {
  userId: string;
  orgId: string;
  apiKey: string;
  apiUrl: string;
}

type ClientType = "claudecode" | "cursor" | "claude" | "antigravity" | "windsurf" | "cline";
type OutputFormat = "cli" | "json";

const CLIENTS = [
  { id: "claudecode", name: "Claude Code", icon: Terminal, hasCli: true, file: "~/.claude.json" },
  { id: "cursor", name: "Cursor", icon: Code2, hasCli: false, file: ".cursor/mcp.json" },
  { id: "claude", name: "Claude Desktop", icon: Bot, hasCli: false, file: "claude_desktop_config.json" },
  { id: "antigravity", name: "Antigravity", icon: Sparkles, hasCli: false, file: "mcp_config.json" },
  { id: "windsurf", name: "Windsurf", icon: Globe, hasCli: false, file: "~/.codeium/windsurf/mcp_config.json" },
  { id: "cline", name: "Cline / Roo", icon: FileCode2, hasCli: false, file: "Settings > MCP Servers" },
] as const;

export function McpClientView({ userId, orgId, apiKey, apiUrl }: McpClientViewProps) {
  const [activeClient, setActiveClient] = useState<ClientType>("claudecode");
  const [outputFormat, setOutputFormat] = useState<OutputFormat>("cli");
  const [isRemote, setIsRemote] = useState(false);
  const [protocol, setProtocol] = useState<"mcp" | "sse">("mcp");
  const [tunnelUrl, setTunnelUrl] = useState("https://your-domain.ngrok-free.app");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Health and ping states
  const [mcpOnline, setMcpOnline] = useState<boolean | null>(null);
  const [mcpLatency, setMcpLatency] = useState<number>(0);
  const [isStartingMcp, setIsStartingMcp] = useState(false);
  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "success" | "error">("idle");
  const [testResult, setTestResult] = useState<string | null>(null);

  // Derived base and active endpoint
  const baseHost = isRemote ? tunnelUrl.replace(/\/$/, "") : "http://localhost:8765";
  const activeEndpointUrl = `${baseHost}/${protocol}`;

  const checkMcpHealth = async () => {
    try {
      const res = await fetch("/api/system/mcp");
      const data = await res.json();
      setMcpOnline(Boolean(data.online));
      if (data.latency_ms) setMcpLatency(data.latency_ms);
    } catch {
      setMcpOnline(false);
    }
  };

  useEffect(() => {
    checkMcpHealth();
    const timer = setInterval(checkMcpHealth, 8000);
    return () => clearInterval(timer);
  }, []);

  // When client changes, auto-select best format (CLI for Claude Code, JSON for others)
  const handleClientSelect = (clientId: ClientType) => {
    setActiveClient(clientId);
    if (clientId === "claudecode") {
      setOutputFormat("cli");
    } else {
      setOutputFormat("json");
    }
  };

  const handleCopy = async (text: string, id: string) => {
    await navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleStartMcp = async () => {
    setIsStartingMcp(true);
    try {
      await fetch("/api/system/mcp", { method: "POST" });
      setTimeout(async () => {
        await checkMcpHealth();
        setIsStartingMcp(false);
      }, 2500);
    } catch {
      setIsStartingMcp(false);
    }
  };

  const handleTestEndpoint = async () => {
    setTestStatus("testing");
    setTestResult(null);
    try {
      if (!isRemote) {
        const res = await fetch("/api/system/mcp");
        const data = await res.json();
        if (data.online) {
          setTestStatus("success");
          setTestResult(`MCP Daemon is active on :8765 (${data.latency_ms ?? 10}ms latency). Ready for agent turns.`);
        } else {
          setTestStatus("error");
          setTestResult("Local MCP Server (:8765) is offline. Click 'Start Daemon' to spin it up.");
        }
      } else {
        await fetch(activeEndpointUrl, { method: "HEAD", mode: "no-cors" });
        setTestStatus("success");
        setTestResult(`Endpoint reachable: ${activeEndpointUrl}`);
      }
    } catch {
      setTestStatus("error");
      setTestResult(`Could not reach ${activeEndpointUrl}. Ensure the host or tunnel is running.`);
    }
  };

  // Snippet generators
  const claudeCodeCliCommand =
    protocol === "mcp"
      ? `claude mcp add contexta "${activeEndpointUrl}" -H "Authorization: Bearer ${apiKey}" -H "X-Org-Id: ${orgId}"`
      : `claude mcp add --transport sse contexta "${activeEndpointUrl}" -H "Authorization: Bearer ${apiKey}" -H "X-Org-Id: ${orgId}"`;

  const getActiveJsonConfig = () => {
    switch (activeClient) {
      case "cursor":
      case "antigravity":
        return JSON.stringify(
          {
            mcpServers: {
              contexta: {
                url: activeEndpointUrl,
                headers: {
                  Authorization: `Bearer ${apiKey}`,
                  "X-User-Id": userId,
                  "X-Org-Id": orgId,
                },
              },
            },
          },
          null,
          2
        );
      case "claude":
        return JSON.stringify(
          {
            mcpServers: {
              contexta: {
                command: "uvx",
                args: [
                  "contexta-mcp",
                  "--api-url",
                  apiUrl,
                  "--api-key",
                  apiKey,
                  "--user-id",
                  userId,
                  "--org-id",
                  orgId,
                ],
              },
            },
          },
          null,
          2
        );
      case "windsurf":
        return JSON.stringify(
          {
            mcpServers: {
              contexta: {
                serverUrl: activeEndpointUrl,
                headers: {
                  Authorization: `Bearer ${apiKey}`,
                  "X-Org-Id": orgId,
                },
              },
            },
          },
          null,
          2
        );
      case "cline":
        return JSON.stringify(
          {
            mcpServers: {
              contexta: {
                type: protocol === "mcp" ? "streamable-http" : "sse",
                url: activeEndpointUrl,
                headers: {
                  Authorization: `Bearer ${apiKey}`,
                  "x-organization-id": orgId,
                },
              },
            },
          },
          null,
          2
        );
      case "claudecode":
      default:
        return JSON.stringify(
          {
            mcpServers: {
              contexta: {
                type: protocol === "mcp" ? "http" : "sse",
                url: activeEndpointUrl,
                headers: {
                  Authorization: `Bearer ${apiKey}`,
                  "X-Org-Id": orgId,
                },
              },
            },
          },
          null,
          2
        );
    }
  };

  const selectedClientMeta = CLIENTS.find((c) => c.id === activeClient) || CLIENTS[0];
  const activeCodeContent = outputFormat === "cli" && selectedClientMeta.hasCli ? claudeCodeCliCommand : getActiveJsonConfig();

  return (
    <div className="space-y-6 font-mono text-xs max-w-5xl mx-auto pb-12 animate-fade-in">
      {/* â”€â”€â”€ Hero / Status Card â”€â”€â”€ */}
      <div className="rounded-lg border border-border bg-card/75  p-6 shadow-sm relative overflow-hidden transition-colors">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="flex size-7 items-center justify-center rounded-lg border border-border bg-secondary text-foreground">
                <Bot className="size-4 tone-green" />
              </span>
              <h2 className="text-base sm:text-lg font-medium tracking-tight text-foreground">
                Model Context Protocol (MCP)
              </h2>
              
              <Badge className="bg-emerald-500/10 tone-green border-emerald-500/30 text-[10px]">
                Streamable HTTP & SSE
              </Badge>

              {mcpOnline ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] bg-emerald-500/10 tone-green border border-emerald-500/30 font-mono">
                  <span className="h-1.5 w-1.5 rounded-full dot dot-green animate-pulse" />
                  Daemon Online (:8765) â€¢ {mcpLatency ? `${mcpLatency}ms` : "<4ms"}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] bg-amber-500/10 tone-amber border border-amber-500/30 font-mono">
                  <span className="h-1.5 w-1.5 rounded-full dot dot-amber" />
                  Daemon Offline (:8765)
                </span>
              )}
            </div>

            <p className="text-xs text-muted-foreground font-sans max-w-2xl leading-relaxed">
              Expose sovereign 3-Layer hybrid memory directly to AI agents. Zero token waste, instant recall, and automatic entity linking.
            </p>
          </div>

          {/* Quick Actions */}
          <div className="flex items-center gap-2 shrink-0">
            {!mcpOnline && (
              <button
                type="button"
                onClick={handleStartMcp}
                disabled={isStartingMcp}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 tone-green transition-all cursor-pointer text-xs font-mono"
              >
                <Play className={`size-3.5 ${isStartingMcp ? "animate-spin" : ""}`} />
                <span>{isStartingMcp ? "Starting..." : "Start Daemon"}</span>
              </button>
            )}

            <button
              type="button"
              onClick={handleTestEndpoint}
              disabled={testStatus === "testing"}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-secondary/80 hover:bg-secondary border border-border text-foreground transition-all cursor-pointer text-xs font-mono"
            >
              <RefreshCw className={`size-3.5 ${testStatus === "testing" ? "animate-spin" : ""}`} />
              <span>{testStatus === "testing" ? "Pinging..." : "Test Connection"}</span>
            </button>
          </div>
        </div>

        {/* Live Test Status Toast Banner */}
        {testResult && (
          <div
            className={`mt-4 p-3 rounded-lg border text-xs flex items-center gap-2.5 ${
              testStatus === "success"
                ? "bg-emerald-500/10 border-emerald-500/30 tone-green"
                : "bg-red-500/10 border-red-500/30 tone-red"
            }`}
          >
            {testStatus === "success" ? (
              <CheckCircle2 className="size-4 shrink-0 tone-green" />
            ) : (
              <Zap className="size-4 shrink-0 tone-red" />
            )}
            <span className="font-sans text-xs">{testResult}</span>
          </div>
        )}
      </div>

      {/* â”€â”€â”€ Simplified OpenCode Setup Workflow â”€â”€â”€ */}
      <div className="rounded-lg border border-border bg-card/75  shadow-sm overflow-hidden transition-colors">
        {/* Step 1: Agent Client Selector Rail */}
        <div className="border-b border-border bg-secondary/30 p-3 sm:p-4">
          <div className="flex items-center justify-between gap-3 mb-3">
            <span className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground">
              1. Choose Agent Client
            </span>
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <span>Target:</span>
              <code className="bg-secondary px-2 py-0.5 rounded border border-border text-foreground">
                {selectedClientMeta.file}
              </code>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            {CLIENTS.map((client) => {
              const Icon = client.icon;
              const isActive = activeClient === client.id;
              return (
                <button
                  type="button"
                  key={client.id}
                  onClick={() => handleClientSelect(client.id as ClientType)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-mono transition-all cursor-pointer ${
                    isActive
                      ? "bg-foreground text-background font-medium shadow-sm"
                      : "bg-secondary/40 text-muted-foreground hover:text-foreground hover:bg-secondary/80 border border-transparent hover:border-border"
                  }`}
                >
                  <Icon className="size-3.5" />
                  <span>{client.name}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Step 2: Code / Command Box with Format Switcher */}
        <div className="p-4 sm:p-5 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-1.5 bg-secondary/60 p-1 rounded-lg border border-border text-[11px]">
              {selectedClientMeta.hasCli && (
                <button
                  type="button"
                  onClick={() => setOutputFormat("cli")}
                  className={`px-2.5 py-1 rounded transition-all cursor-pointer flex items-center gap-1 ${
                    outputFormat === "cli"
                      ? "bg-foreground text-background font-medium"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Terminal className="size-3" />
                  <span>CLI Command (1-Click)</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => setOutputFormat("json")}
                className={`px-2.5 py-1 rounded transition-all cursor-pointer flex items-center gap-1 ${
                  outputFormat === "json"
                    ? "bg-foreground text-background font-medium"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Code2 className="size-3" />
                <span>Config JSON</span>
              </button>
            </div>

            <button
              type="button"
              onClick={() => handleCopy(activeCodeContent, "main-code")}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 tone-green font-medium text-xs transition-all cursor-pointer"
            >
              {copiedId === "main-code" ? (
                <>
                  <Check className="size-3.5 tone-green" />
                  <span>Copied to Clipboard!</span>
                </>
              ) : (
                <>
                  <Copy className="size-3.5" />
                  <span>{outputFormat === "cli" ? "Copy Command" : "Copy JSON"}</span>
                </>
              )}
            </button>
          </div>

          {/* Code Viewer Container */}
          <div className="relative rounded-lg border border-border bg-secondary/20 p-4 font-mono text-xs overflow-x-auto">
            {outputFormat === "cli" ? (
              <div className="flex items-center gap-2 select-all tone-green">
                <span className="text-muted-foreground select-none">$</span>
                <span className="whitespace-pre-wrap break-all">{claudeCodeCliCommand}</span>
              </div>
            ) : (
              <pre className="text-zinc-300 dark:text-zinc-200 leading-relaxed overflow-x-auto pr-4">
                <code>{getActiveJsonConfig()}</code>
              </pre>
            )}
          </div>

          {/* Quick instructions */}
          <div className="flex items-center justify-between text-[11px] text-muted-foreground font-sans pt-1">
            <span>
              {outputFormat === "cli"
                ? "Run this command in your terminal to instantly register Contexta into Claude Code."
                : `Paste this block into ${selectedClientMeta.file} and restart your editor.`}
            </span>
            <span className="hidden sm:inline-block font-mono text-[10px]">Auto-authenticated with active API key</span>
          </div>
        </div>

        {/* Step 3: Streamlined Connection Customization Bar */}
        <div className="border-t border-border bg-secondary/15 p-4 sm:p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sliders className="size-3.5 text-muted-foreground" />
              <span className="text-xs font-medium text-foreground">Connection & Reachability</span>
            </div>

            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors cursor-pointer"
            >
              <span>{showAdvanced ? "Hide advanced" : "Advanced options"}</span>
              {showAdvanced ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
            </button>
          </div>

          {/* Primary Quick Toggles */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Local vs Remote Segmented Control */}
            <div className="flex items-center bg-secondary/60 p-1 rounded-lg border border-border text-[11px]">
              <button
                type="button"
                onClick={() => setIsRemote(false)}
                className={`px-3 py-1 rounded-md transition-all cursor-pointer flex items-center gap-1.5 ${
                  !isRemote
                    ? "bg-foreground text-background font-medium"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Radio className="size-3" />
                <span>Localhost (:8765)</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsRemote(true);
                  setShowAdvanced(true);
                }}
                className={`px-3 py-1 rounded-md transition-all cursor-pointer flex items-center gap-1.5 ${
                  isRemote
                    ? "bg-foreground text-background font-medium"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Globe className="size-3" />
                <span>Remote / Tunnel</span>
              </button>
            </div>

            {/* Protocol format toggle */}
            <div className="flex items-center bg-secondary/60 p-1 rounded-lg border border-border text-[11px]">
              <button
                type="button"
                onClick={() => setProtocol("mcp")}
                className={`px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                  protocol === "mcp"
                    ? "bg-foreground text-background font-medium"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                HTTP (/mcp)
              </button>
              <button
                type="button"
                onClick={() => setProtocol("sse")}
                className={`px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                  protocol === "sse"
                    ? "bg-foreground text-background font-medium"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                SSE (/sse)
              </button>
            </div>

            {/* Quick URL Pill */}
            <div className="flex items-center gap-2 ml-auto">
              <span className="text-[10px] text-muted-foreground uppercase">Endpoint:</span>
              <div className="flex items-center gap-1 bg-secondary/60 px-2.5 py-1 rounded-lg border border-border text-[11px]">
                <span className="tone-green font-mono truncate max-w-[200px]">{activeEndpointUrl}</span>
                <button
                  type="button"
                  onClick={() => handleCopy(activeEndpointUrl, "endpoint-pill")}
                  className="text-muted-foreground hover:text-foreground ml-1"
                  title="Copy Endpoint URL"
                >
                  {copiedId === "endpoint-pill" ? <Check className="size-3 tone-green" /> : <Copy className="size-3" />}
                </button>
              </div>
            </div>
          </div>

          {/* Expandable Advanced Tunnel Config */}
          {showAdvanced && (
            <div className="pt-3 border-t border-border space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="space-y-0.5">
                  <span className="text-xs font-medium text-foreground">Custom Tunnel or Public Domain URL</span>
                  <p className="text-[11px] text-muted-foreground font-sans">
                    Connecting from a cloud runner or remote agent? Enter your tunnel URL below.
                  </p>
                </div>
                <input
                  type="text"
                  value={tunnelUrl}
                  onChange={(e) => setTunnelUrl(e.target.value)}
                  placeholder="https://xxxx.ngrok-free.app"
                  className="bg-background border border-border/50 text-foreground px-3 py-1.5 rounded-lg font-mono text-xs w-full sm:w-72 focus:outline-hidden focus:border-emerald-400 transition-colors"
                />
              </div>

              <div className="flex flex-wrap items-center gap-2 pt-1 text-[11px]">
                <span className="text-[10px] text-muted-foreground uppercase">Quick Tunnel Commands:</span>
                <button
                  type="button"
                  onClick={() => handleCopy("ngrok http 8765", "ngrok")}
                  className="flex items-center gap-1 px-2 py-0.5 rounded bg-secondary border border-border text-foreground hover:border-border"
                >
                  <span>ngrok http 8765</span>
                  {copiedId === "ngrok" ? <Check className="size-2.5 tone-green" /> : <Copy className="size-2.5" />}
                </button>
                <button
                  type="button"
                  onClick={() => handleCopy("cloudflared tunnel --url http://localhost:8765", "cf")}
                  className="flex items-center gap-1 px-2 py-0.5 rounded bg-secondary border border-border text-foreground hover:border-border"
                >
                  <span>cloudflared tunnel --url http://localhost:8765</span>
                  {copiedId === "cf" ? <Check className="size-2.5 tone-green" /> : <Copy className="size-2.5" />}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* â”€â”€â”€ Exposed Tools Bento Grid â”€â”€â”€ */}
      <div className="space-y-3 pt-2">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <Layers className="size-3.5" />
            <span>Exposed MCP Tools</span>
          </h3>
          <span className="text-[10px] text-muted-foreground font-mono">
            Auto-Registered for Connected Agents
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="rounded-lg border border-border bg-card p-4 space-y-2 hover:border-border/80 transition-colors">
            <div className="flex items-center justify-between">
              <span className="font-mono font-medium tone-green flex items-center gap-1.5">
                contexta_recall
              </span>
              <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-500/10 tone-green border border-emerald-500/20">
                Read
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground font-sans leading-relaxed">
              Fuses dense vector cosine similarity, BM25 lexical keyword matching, and knowledge graph traversal scored by neural reranker.
            </p>
            <div className="text-[10px] text-muted-foreground font-mono bg-secondary/40 p-2 rounded-lg border border-border">
              <code>query: string, limit?: number, graph_depth?: number</code>
            </div>
          </div>

          <div className="rounded-lg border border-border bg-card p-4 space-y-2 hover:border-border/80 transition-colors">
            <div className="flex items-center justify-between">
              <span className="font-mono font-medium tone-blue flex items-center gap-1.5">
                contexta_remember
              </span>
              <span className="text-[9px] px-2 py-0.5 rounded-full bg-indigo-500/10 tone-blue border border-indigo-500/20">
                Write
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground font-sans leading-relaxed">
              Ingests dialogue turns, redacts credentials and PII, extracts facts, rules and preferences, and resolves entity graph nodes.
            </p>
            <div className="text-[10px] text-muted-foreground font-mono bg-secondary/40 p-2 rounded-lg border border-border">
              <code>content: string, user_id: string, title?: string, memory_type?: string</code>
            </div>
          </div>

          <div className="rounded-lg border border-border bg-card p-4 space-y-2 hover:border-border/80 transition-colors">
            <div className="flex items-center justify-between">
              <span className="font-mono font-medium tone-blue flex items-center gap-1.5">
                contexta_batch_remember
              </span>
              <span className="text-[9px] px-2 py-0.5 rounded-full bg-sky-500/10 tone-blue border border-sky-500/20">
                Write
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground font-sans leading-relaxed">
              Queues several memories in one call and returns a job id for polling with contexta_job_status.
            </p>
            <div className="text-[10px] text-muted-foreground font-mono bg-secondary/40 p-2 rounded-lg border border-border">
              <code>memories: [&#123;content, title, memory_type&#125;]</code>
            </div>
          </div>

          <div className="rounded-lg border border-border bg-card p-4 space-y-2 hover:border-border/80 transition-colors">
            <div className="flex items-center justify-between">
              <span className="font-mono font-medium tone-blue flex items-center gap-1.5">
                contexta_get_context
              </span>
              <span className="text-[9px] px-2 py-0.5 rounded-full bg-sky-500/10 tone-blue border border-sky-500/20">
                Read
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground font-sans leading-relaxed">
              Assembles a token-budgeted memory context package: profile, rules, projects, preferences, goals and recent events.
            </p>
            <div className="text-[10px] text-muted-foreground font-mono bg-secondary/40 p-2 rounded-lg border border-border">
              <code>user_id: string, focus?: string, max_memories?: number</code>
            </div>
          </div>

          <div className="rounded-lg border border-border bg-card p-4 space-y-2 hover:border-border/80 transition-colors">
            <div className="flex items-center justify-between">
              <span className="font-mono font-medium tone-green flex items-center gap-1.5">
                contexta_explore_graph
              </span>
              <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-500/10 tone-green border border-emerald-500/20">
                Read
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground font-sans leading-relaxed">
              Traverses multi-hop entity relationships and the facts linked to each node in your knowledge graph.
            </p>
            <div className="text-[10px] text-muted-foreground font-mono bg-secondary/40 p-2 rounded-lg border border-border">
              <code>entity_name: string, depth?: number, user_id?: string</code>
            </div>
          </div>

          <div className="rounded-lg border border-border bg-card p-4 space-y-2 hover:border-border/80 transition-colors">
            <div className="flex items-center justify-between">
              <span className="font-mono font-medium text-rose-400 flex items-center gap-1.5">
                contexta_forget
              </span>
              <span className="text-[9px] px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20">
                Tombstone
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground font-sans leading-relaxed">
              Invalidates a memory. The truth engine closes its validity window and links the replacement through the supersession lineage.
            </p>
            <div className="text-[10px] text-muted-foreground font-mono bg-secondary/40 p-2 rounded-lg border border-border">
              <code>memory_id: string, reason?: string</code>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

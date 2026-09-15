"use client";

import React, { useState, useEffect } from "react";
import {
  Bot,
  Terminal,
  Cpu,
  Layers,
  CheckCircle2,
  Copy,
  Check,
  Zap,
  ExternalLink,
  ShieldCheck,
  RefreshCw,
  Sparkles,
  Globe,
  Radio,
  Lock,
  Play,
  Server,
  ArrowUpRight,
  Code2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface McpClientViewProps {
  userId: string;
  orgId: string;
  apiKey: string;
  apiUrl: string;
}

type ClientType = "claudecode" | "cursor" | "claude" | "antigravity" | "windsurf" | "cline";
type EndpointMode = "local" | "tunnel" | "gateway";
type ProtocolType = "streamable" | "sse";

export function McpClientView({ userId, orgId, apiKey, apiUrl }: McpClientViewProps) {
  const [activeClient, setActiveClient] = useState<ClientType>("claudecode");
  const [endpointMode, setEndpointMode] = useState<EndpointMode>("local");
  const [protocol, setProtocol] = useState<ProtocolType>("streamable");
  const [tunnelUrl, setTunnelUrl] = useState("https://your-domain.ngrok-free.app");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Server health state
  const [mcpOnline, setMcpOnline] = useState<boolean | null>(null);
  const [mcpLatency, setMcpLatency] = useState<number>(0);
  const [isStartingMcp, setIsStartingMcp] = useState(false);
  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "success" | "error">("idle");
  const [testResult, setTestResult] = useState<string | null>(null);

  const localBase = "http://localhost:8765";
  const gatewayBase = "https://localhost:8443";

  // Compute active base URL
  const activeBaseUrl =
    endpointMode === "local"
      ? localBase
      : endpointMode === "gateway"
      ? gatewayBase
      : tunnelUrl.replace(/\/$/, "");

  // Compute full endpoint based on protocol (/mcp for Streamable HTTP, /sse for SSE)
  const activeEndpointUrl = `${activeBaseUrl}${protocol === "streamable" ? "/mcp" : "/sse"}`;

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
    const timer = setInterval(checkMcpHealth, 6000);
    return () => clearInterval(timer);
  }, []);

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

  const handleCopy = async (text: string, id: string) => {
    await navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleTestEndpoint = async () => {
    setTestStatus("testing");
    setTestResult(null);
    try {
      if (endpointMode === "local") {
        const res = await fetch("/api/system/mcp");
        const data = await res.json();
        if (data.online) {
          setTestStatus("success");
          setTestResult(`MCP Daemon is active on :8765 (${data.latency_ms ?? 10}ms latency). Ready for agent queries.`);
        } else {
          setTestStatus("error");
          setTestResult("Local MCP Server (:8765) is offline. Click 'Start MCP Server' below.");
        }
      } else {
        // Probe user's custom tunnel or gateway
        const res = await fetch(activeEndpointUrl, { method: "HEAD", mode: "no-cors" });
        setTestStatus("success");
        setTestResult(`Reachable: ${activeEndpointUrl}`);
      }
    } catch (err: any) {
      setTestStatus("error");
      setTestResult(`Could not connect to ${activeEndpointUrl}. Ensure tunnel is running.`);
    }
  };

  // Config generators
  const claudeCodeCliCommand =
    protocol === "streamable"
      ? `claude mcp add contexta "${activeEndpointUrl}" -H "Authorization: Bearer ${apiKey}" -H "X-Org-Id: ${orgId}"`
      : `claude mcp add --transport sse contexta "${activeEndpointUrl}" -H "Authorization: Bearer ${apiKey}" -H "X-Org-Id: ${orgId}"`;

  const claudeCodeConfig = JSON.stringify(
    {
      mcpServers: {
        contexta: {
          type: protocol === "streamable" ? "http" : "sse",
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

  const cursorConfig = JSON.stringify(
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

  const claudeDesktopConfig = JSON.stringify(
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

  const antigravityConfig = JSON.stringify(
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

  const windsurfConfig = JSON.stringify(
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

  const clineConfig = JSON.stringify(
    {
      mcpServers: {
        contexta: {
          type: protocol === "streamable" ? "streamable-http" : "sse",
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

  const activeSnippet =
    activeClient === "claudecode"
      ? claudeCodeConfig
      : activeClient === "cursor"
      ? cursorConfig
      : activeClient === "claude"
      ? claudeDesktopConfig
      : activeClient === "antigravity"
      ? antigravityConfig
      : activeClient === "windsurf"
      ? windsurfConfig
      : clineConfig;

  const configFilePath =
    activeClient === "claudecode"
      ? "~/.claude.json or claude.json"
      : activeClient === "cursor"
      ? ".cursor/mcp.json (Workspace) or Settings > Features > MCP"
      : activeClient === "claude"
      ? "%APPDATA%\\Claude\\claude_desktop_config.json"
      : activeClient === "antigravity"
      ? "~/.gemini/antigravity-ide/mcp_config.json"
      : activeClient === "windsurf"
      ? "~/.codeium/windsurf/mcp_config.json"
      : "Roo Code / Cline Settings > MCP Servers";

  return (
    <div className="space-y-6 font-mono text-xs max-w-5xl mx-auto pb-12 animate-fade-in">
      {/* Header Banner with Clean Status */}
      <div className="rounded-2xl border border-border/40 bg-card/85 backdrop-blur-xl p-6 shadow-xl relative overflow-hidden">
        <div className="absolute right-0 top-0 translate-x-12 -translate-y-12 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
        
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 relative z-10">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="flex size-7 items-center justify-center rounded-lg border border-border/40 bg-secondary/80 text-indigo-400">
                <Bot className="size-4" />
              </span>
              <h2 className="text-lg font-medium text-foreground tracking-tight">Model Context Protocol (MCP)</h2>
              
              <Badge variant="outline" className="bg-emerald-500/10 text-emerald-400 border-emerald-500/30 text-[10px]">
                Streamable HTTP & SSE
              </Badge>

              {mcpOnline ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 font-mono">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Daemon Online (:8765)
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] bg-amber-500/15 text-amber-400 border border-amber-500/30 font-mono">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                  Daemon Offline (:8765)
                </span>
              )}
            </div>
            
            <p className="text-xs text-muted-foreground max-w-2xl font-sans leading-relaxed">
              Expose Contexta&apos;s 3-Layer hybrid memory directly to AI agents (Claude Code, Cursor, Windsurf, Claude Desktop, Antigravity) with zero credential leaks.
            </p>
          </div>

          <div className="flex items-center gap-2.5 shrink-0">
            {!mcpOnline && (
              <button
                type="button"
                onClick={handleStartMcp}
                disabled={isStartingMcp}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-300 transition-all cursor-pointer shadow-xs text-xs font-mono"
              >
                <Play className={`h-3.5 w-3.5 ${isStartingMcp ? "animate-spin" : ""}`} />
                <span>{isStartingMcp ? "Starting..." : "Start MCP Server"}</span>
              </button>
            )}

            <button
              type="button"
              onClick={handleTestEndpoint}
              disabled={testStatus === "testing"}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-secondary hover:bg-secondary/80 border border-border/40 text-foreground transition-all cursor-pointer shadow-xs text-xs font-mono"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${testStatus === "testing" ? "animate-spin" : ""}`} />
              <span>{testStatus === "testing" ? "Pinging..." : "Test Endpoint"}</span>
            </button>
          </div>
        </div>

        {/* Live Test Result Alert */}
        {testResult && (
          <div
            className={`mt-4 p-3 rounded-xl border text-xs flex items-center gap-2.5 ${
              testStatus === "success"
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                : "bg-red-500/10 border-red-500/30 text-red-300"
            }`}
          >
            {testStatus === "success" ? (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
            ) : (
              <Zap className="h-4 w-4 shrink-0 text-red-400" />
            )}
            <span className="font-sans text-xs">{testResult}</span>
          </div>
        )}
      </div>

      {/* Endpoint Selector & Configuration Matrix */}
      <div className="rounded-2xl border border-border/40 bg-card/75 backdrop-blur-xl p-5 shadow-xl space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-border/30 pb-4">
          <div>
            <span className="text-xs font-medium text-foreground uppercase tracking-wider">Transport & Reachability</span>
            <p className="text-[11px] text-muted-foreground font-sans mt-0.5">
              Select whether you are connecting via localhost or an HTTPS tunnel (required for cloud/remote clients).
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Protocol format toggle */}
            <div className="flex items-center bg-secondary/60 p-1 rounded-lg border border-border/30 text-[11px]">
              <button
                type="button"
                onClick={() => setProtocol("streamable")}
                className={`px-2.5 py-1 rounded transition-all cursor-pointer ${
                  protocol === "streamable"
                    ? "bg-foreground text-background font-medium"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Streamable HTTP (/mcp)
              </button>
              <button
                type="button"
                onClick={() => setProtocol("sse")}
                className={`px-2.5 py-1 rounded transition-all cursor-pointer ${
                  protocol === "sse"
                    ? "bg-foreground text-background font-medium"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                SSE (/sse)
              </button>
            </div>

            {/* Endpoint mode toggle */}
            <div className="flex items-center bg-secondary/60 p-1 rounded-lg border border-border/30 text-[11px]">
              <button
                type="button"
                onClick={() => setEndpointMode("local")}
                className={`px-2.5 py-1 rounded transition-all cursor-pointer flex items-center gap-1.5 ${
                  endpointMode === "local"
                    ? "bg-foreground text-background font-medium"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Radio className="h-3 w-3" />
                <span>Local (:8765)</span>
              </button>
              <button
                type="button"
                onClick={() => setEndpointMode("tunnel")}
                className={`px-2.5 py-1 rounded transition-all cursor-pointer flex items-center gap-1.5 ${
                  endpointMode === "tunnel"
                    ? "bg-foreground text-background font-medium"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Globe className="h-3 w-3" />
                <span>HTTPS Tunnel (ngrok)</span>
              </button>
              <button
                type="button"
                onClick={() => setEndpointMode("gateway")}
                className={`px-2.5 py-1 rounded transition-all cursor-pointer flex items-center gap-1.5 ${
                  endpointMode === "gateway"
                    ? "bg-foreground text-background font-medium"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Lock className="h-3 w-3" />
                <span>Gateway (:8443)</span>
              </button>
            </div>
          </div>
        </div>

        {/* Tunnel Configuration Input (when tunnel mode selected) */}
        {endpointMode === "tunnel" && (
          <div className="rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-4 space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="space-y-1">
                <span className="text-xs font-medium text-indigo-300 flex items-center gap-1.5">
                  <Globe className="h-3.5 w-3.5" />
                  <span>Custom HTTPS Domain or ngrok Tunnel</span>
                </span>
                <p className="text-[11px] text-muted-foreground font-sans">
                  Paste your public HTTPS tunnel URL below. Configs and CLI commands automatically update.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={tunnelUrl}
                  onChange={(e) => setTunnelUrl(e.target.value)}
                  placeholder="https://xxxx.ngrok-free.app"
                  className="bg-background/80 border border-border/50 text-foreground px-3 py-1.5 rounded-lg font-mono text-xs w-64 sm:w-72 focus:outline-hidden focus:border-indigo-500"
                />
              </div>
            </div>

            {/* Quick 1-Click Launch Helpers */}
            <div className="pt-2 border-t border-indigo-500/20 space-y-2">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wider">
                Launch local tunnel in 1 command:
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                <div className="flex items-center justify-between bg-background/60 p-2 rounded-lg border border-border/30">
                  <span className="text-zinc-300 font-mono">ngrok http 8765</span>
                  <button
                    type="button"
                    onClick={() => handleCopy("ngrok http 8765", "ngrok-cmd")}
                    className="text-muted-foreground hover:text-foreground p-1"
                    title="Copy ngrok command"
                  >
                    {copiedId === "ngrok-cmd" ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                  </button>
                </div>
                <div className="flex items-center justify-between bg-background/60 p-2 rounded-lg border border-border/30">
                  <span className="text-zinc-300 font-mono">cloudflared tunnel --url http://localhost:8765</span>
                  <button
                    type="button"
                    onClick={() => handleCopy("cloudflared tunnel --url http://localhost:8765", "cf-cmd")}
                    className="text-muted-foreground hover:text-foreground p-1"
                    title="Copy cloudflare command"
                  >
                    {copiedId === "cf-cmd" ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Active URL & Meta Card */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
          <div className="rounded-xl border border-border/40 bg-secondary/30 p-3 space-y-1">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Active Endpoint URL</span>
            <div className="flex items-center justify-between bg-background/80 px-2.5 py-1.5 rounded-lg border border-border/30">
              <span className="text-xs text-emerald-400 font-mono truncate select-all">{activeEndpointUrl}</span>
              <button
                type="button"
                onClick={() => handleCopy(activeEndpointUrl, "endpoint-url")}
                className="text-muted-foreground hover:text-foreground ml-2 shrink-0 cursor-pointer"
                title="Copy URL"
              >
                {copiedId === "endpoint-url" ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-border/40 bg-secondary/30 p-3 space-y-1">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Stdio Driver Package</span>
            <div className="flex items-center justify-between bg-background/80 px-2.5 py-1.5 rounded-lg border border-border/30">
              <span className="text-xs text-foreground font-mono truncate select-all">uvx contexta-mcp</span>
              <button
                type="button"
                onClick={() => handleCopy("uvx contexta-mcp", "stdio-pkg")}
                className="text-muted-foreground hover:text-foreground ml-2 shrink-0 cursor-pointer"
                title="Copy command"
              >
                {copiedId === "stdio-pkg" ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-border/40 bg-secondary/30 p-3 space-y-1">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Tenant Organization ID</span>
            <div className="flex items-center justify-between bg-background/80 px-2.5 py-1.5 rounded-lg border border-border/30">
              <span className="text-xs text-foreground font-mono truncate select-all">{orgId || "default-org"}</span>
              <button
                type="button"
                onClick={() => handleCopy(orgId || "default-org", "tenant-id")}
                className="text-muted-foreground hover:text-foreground ml-2 shrink-0 cursor-pointer"
                title="Copy Org ID"
              >
                {copiedId === "tenant-id" ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Integration Client Picker & Config */}
      <div className="rounded-2xl border border-border/40 bg-card/75 backdrop-blur-xl shadow-xl overflow-hidden">
        <div className="border-b border-border/30 bg-secondary/20 p-4 flex flex-wrap items-center justify-between gap-3">
          {/* Client Tabs */}
          <div className="flex flex-wrap items-center gap-1.5 bg-secondary/60 p-1 rounded-xl border border-border/30">
            <button
              type="button"
              onClick={() => setActiveClient("claudecode")}
              className={`px-3 py-1.5 rounded-lg text-xs transition-all cursor-pointer flex items-center gap-1.5 ${
                activeClient === "claudecode"
                  ? "bg-foreground text-background font-medium shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Terminal className="h-3.5 w-3.5" />
              <span>Claude Code CLI</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveClient("cursor")}
              className={`px-3 py-1.5 rounded-lg text-xs transition-all cursor-pointer ${
                activeClient === "cursor"
                  ? "bg-foreground text-background font-medium shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Cursor IDE
            </button>
            <button
              type="button"
              onClick={() => setActiveClient("claude")}
              className={`px-3 py-1.5 rounded-lg text-xs transition-all cursor-pointer ${
                activeClient === "claude"
                  ? "bg-foreground text-background font-medium shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Claude Desktop
            </button>
            <button
              type="button"
              onClick={() => setActiveClient("antigravity")}
              className={`px-3 py-1.5 rounded-lg text-xs transition-all cursor-pointer ${
                activeClient === "antigravity"
                  ? "bg-foreground text-background font-medium shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Antigravity / Gemini
            </button>
            <button
              type="button"
              onClick={() => setActiveClient("windsurf")}
              className={`px-3 py-1.5 rounded-lg text-xs transition-all cursor-pointer ${
                activeClient === "windsurf"
                  ? "bg-foreground text-background font-medium shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Windsurf
            </button>
            <button
              type="button"
              onClick={() => setActiveClient("cline")}
              className={`px-3 py-1.5 rounded-lg text-xs transition-all cursor-pointer ${
                activeClient === "cline"
                  ? "bg-foreground text-background font-medium shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Roo Code / Cline
            </button>
          </div>

          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <span>Target Config:</span>
            <code className="bg-secondary px-2 py-0.5 rounded text-foreground border border-border/30">
              {configFilePath}
            </code>
          </div>
        </div>

        {/* Special 1-Click CLI Section for Claude Code */}
        {activeClient === "claudecode" && (
          <div className="p-4 border-b border-border/30 bg-indigo-950/20 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-indigo-300 flex items-center gap-1.5">
                <Sparkles className="h-3.5 w-3.5" />
                <span>Instant Terminal Command (Claude Code CLI)</span>
              </span>
              <span className="text-[10px] text-muted-foreground font-sans">
                Installs Contexta directly into your active Claude Code session
              </span>
            </div>
            <div className="flex items-center justify-between bg-black/70 p-3 rounded-xl border border-indigo-500/30">
              <code className="text-emerald-400 font-mono text-xs select-all overflow-x-auto pr-4">
                {claudeCodeCliCommand}
              </code>
              <button
                type="button"
                onClick={() => handleCopy(claudeCodeCliCommand, "cli-cmd")}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-secondary hover:bg-secondary/80 text-xs text-foreground border border-border/40 shrink-0 transition-all cursor-pointer"
              >
                {copiedId === "cli-cmd" ? (
                  <>
                    <Check className="h-3.5 w-3.5 text-emerald-400" />
                    <span className="text-emerald-400">Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5" />
                    <span>Copy Command</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Code Snippet Box */}
        <div className="relative p-5 bg-[#09090b]">
          <button
            type="button"
            onClick={() => handleCopy(activeSnippet, "active-snippet")}
            className="absolute top-4 right-4 flex items-center gap-1 px-3 py-1.5 rounded-lg bg-secondary/80 hover:bg-secondary text-xs text-foreground border border-border/40 transition-all cursor-pointer z-10"
          >
            {copiedId === "active-snippet" ? (
              <>
                <Check className="h-3.5 w-3.5 text-emerald-400" />
                <span className="text-emerald-400">Copied</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                <span>Copy JSON</span>
              </>
            )}
          </button>

          <pre className="overflow-x-auto text-[11px] font-mono text-zinc-200 leading-relaxed pr-24">
            <code>{activeSnippet}</code>
          </pre>
        </div>
      </div>

      {/* Exposed Tools Catalog */}
      <div className="space-y-3 pt-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-foreground tracking-tight flex items-center gap-2">
            <Layers className="h-4 w-4 text-indigo-400" />
            <span>Exposed MCP Tools Catalog</span>
          </h3>
          <span className="text-[10px] text-muted-foreground font-mono">Auto-Registered via Model Context Protocol</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="rounded-xl border border-border/40 bg-card/60 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-mono font-medium text-emerald-400 flex items-center gap-1.5">
                <span>contexta_retrieve</span>
              </span>
              <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Read</span>
            </div>
            <p className="text-[11px] text-muted-foreground font-sans leading-relaxed">
              Fuses dense vector cosine similarity, BM25 lexical keyword matching, and knowledge graph traversal scored by neural reranker.
            </p>
            <div className="text-[10px] text-muted-foreground font-mono bg-secondary/40 p-2 rounded-lg border border-border/20">
              Params: <code>query: string, token_budget?: number, tags?: string[]</code>
            </div>
          </div>

          <div className="rounded-xl border border-border/40 bg-card/60 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-mono font-medium text-indigo-400 flex items-center gap-1.5">
                <span>contexta_observe</span>
              </span>
              <span className="text-[9px] px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">Write</span>
            </div>
            <p className="text-[11px] text-muted-foreground font-sans leading-relaxed">
              Ingests dialogue turns, sanitizes credentials/PII, extracts facts, rules, and preferences, and resolves entity graph nodes.
            </p>
            <div className="text-[10px] text-muted-foreground font-mono bg-secondary/40 p-2 rounded-lg border border-border/20">
              Params: <code>messages: [&#123;role, content&#125;], session_id?: string</code>
            </div>
          </div>

          <div className="rounded-xl border border-border/40 bg-card/60 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-mono font-medium text-sky-400 flex items-center gap-1.5">
                <span>contexta_get_entities</span>
              </span>
              <span className="text-[9px] px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-400 border border-sky-500/20">Read</span>
            </div>
            <p className="text-[11px] text-muted-foreground font-sans leading-relaxed">
              Traverses multi-hop entity relationships and associated facts within your sovereign knowledge graph.
            </p>
            <div className="text-[10px] text-muted-foreground font-mono bg-secondary/40 p-2 rounded-lg border border-border/20">
              Params: <code>entity_name: string, depth?: number</code>
            </div>
          </div>

          <div className="rounded-xl border border-border/40 bg-card/60 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-mono font-medium text-rose-400 flex items-center gap-1.5">
                <span>contexta_forget</span>
              </span>
              <span className="text-[9px] px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20">Tombstone</span>
            </div>
            <p className="text-[11px] text-muted-foreground font-sans leading-relaxed">
              Invalidates outdated memories or corrects contradictory information via lineage superseding.
            </p>
            <div className="text-[10px] text-muted-foreground font-mono bg-secondary/40 p-2 rounded-lg border border-border/20">
              Params: <code>memory_id: string, reason?: string</code>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

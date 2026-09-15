"use client";

import React, { useState } from "react";
import {
  BookOpen,
  Copy,
  Check,
  RefreshCw,
  Server,
  Bot,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";

interface SetupViewProps {
  userId: string;
  orgId: string;
  apiKey: string;
  apiUrl: string;
}

export function SetupView({ userId, orgId, apiKey, apiUrl }: SetupViewProps) {
  const [sdkLanguage, setSdkLanguage] = useState<"python" | "typescript">("python");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "online" | "offline">("idle");
  const [testMessage, setTestMessage] = useState<string | null>(null);

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleTestConnection = async () => {
    setTestStatus("testing");
    setTestMessage("Pinging local Contexta Brain (:8000)...");
    try {
      const res = await fetch("/api/system/engine");
      const data = await res.json();
      if (data.online) {
        setTestStatus("online");
        setTestMessage("Connected! Contexta engine is online and healthy.");
      } else {
        setTestStatus("offline");
        setTestMessage("Offline. Click 'Start Engine' in the header to launch natively in the background.");
      }
    } catch {
      setTestStatus("offline");
      setTestMessage("Could not reach engine. Ensure port 8000 is listening.");
    }
  };

  const nativeCommand = `uv run python -m uvicorn contexta.api.app:app --host 127.0.0.1 --port 8000`;
  const powershellCommand = `.\\start.ps1`;

  const pythonSdkSnippet = `from contexta_client import Contexta

client = Contexta(
    api_url="${apiUrl}",
    api_key="${apiKey}"
)

# 1. Ingest an observation into the memory enclave
client.observe(
    user_id="${userId}",
    organization_id="${orgId}",
    messages=[
        {"role": "user", "content": "I prefer PostgreSQL over MongoDB and love dark mode."},
        {"role": "assistant", "content": "Noted! Saved to your memory enclave."}
    ]
)

# 2. Retrieve personalized context using hybrid neural search
context = client.context(
    user_id="${userId}",
    query="What database does the user prefer?",
    token_budget=1500
)

print(context)`;

  const tsSdkSnippet = `import { Contexta } from "contexta-client";

const contexta = new Contexta({
  apiUrl: "${apiUrl}",
  apiKey: "${apiKey}",
});

// 1. Submit an observation
await contexta.observe({
  userId: "${userId}",
  organizationId: "${orgId}",
  messages: [
    { role: "user", content: "I prefer PostgreSQL and build in TypeScript." },
    { role: "assistant", content: "Preferences memorized." },
  ],
});

// 2. Hybrid search & retrieve context
const memories = await contexta.retrieve({
  userId: "${userId}",
  organizationId: "${orgId}",
  query: "user database preference",
});

console.log(memories);`;

  const curlObserveSnippet = `curl -X POST ${apiUrl}/v1/observations \\
  -H "Authorization: Bearer ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "user_id": "${userId}",
    "organization_id": "${orgId}",
    "messages": [
      {"role": "user", "content": "My primary production cluster is in us-east-1."},
      {"role": "assistant", "content": "Noted."}
    ]
  }'`;

  return (
    <div className="w-full max-w-3xl mx-auto flex flex-col items-center space-y-8 animate-fade-in font-mono text-xs pb-16">
      {/* Header - Center Aligned */}
      <div className="w-full border-b border-border/40 pb-6 text-center flex flex-col items-center">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] bg-blue-500/10 border border-blue-500/20 text-blue-400 mb-3">
          <BookOpen className="h-3.5 w-3.5" />
          <span>Quickstart & Integration</span>
        </div>
        <h2 className="text-2xl font-normal tracking-tight text-foreground">Setup Guide</h2>
        <p className="mt-2 text-xs text-muted-foreground font-sans max-w-md text-center leading-relaxed">
          Get your autonomous memory enclave running in minutes. Follow the friendly checklist below to link your local daemon and AI agents.
        </p>
      </div>

      {/* Connectivity Banner */}
      <div className="w-full rounded-2xl border border-border/40 bg-secondary/20 p-4 flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="flex items-center gap-3 text-center sm:text-left">
          <div className="p-2 rounded-xl bg-secondary border border-border/40 text-foreground">
            <Server className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center justify-center sm:justify-start gap-2">
              <span className="text-xs font-medium text-foreground">Contexta Engine Connectivity</span>
              {testStatus === "online" && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  Online
                </span>
              )}
              {testStatus === "offline" && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  Not Detected
                </span>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground font-sans">
              {testMessage || "Check if local engine (:8000) and Qwen3 models are ready."}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={handleTestConnection}
          disabled={testStatus === "testing"}
          className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border/60 bg-secondary/60 hover:bg-secondary text-xs text-foreground font-mono transition-colors cursor-pointer"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${testStatus === "testing" ? "animate-spin" : ""}`} />
          <span>{testStatus === "testing" ? "Testing..." : "Test Connection"}</span>
        </button>
      </div>

      {/* Step 1: Launch Backend Engine */}
      <Card className="w-full">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-foreground text-background text-xs font-bold">
                1
              </span>
              <div>
                <CardTitle className="text-sm font-medium text-foreground">
                  Launch Sovereign Contexta Engine
                </CardTitle>
                <CardDescription className="text-xs">
                  Runs natively in the background—no Docker required.
                </CardDescription>
              </div>
            </div>
            <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30 text-[10px]">
              Offline-First & Native
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground font-sans">
              Click &quot;Start Engine&quot; in the header bar for instant background execution, or run natively:
            </p>
            {/* Native Python Command */}
            <div className="rounded-xl border border-border/40 bg-background/80 p-3 flex items-center justify-between font-mono text-xs">
              <div className="overflow-x-auto mr-2">
                <span className="text-muted-foreground select-none"># Native Python: </span>
                <span className="text-emerald-400 select-all">{nativeCommand}</span>
              </div>
              <button
                type="button"
                onClick={() => handleCopy(nativeCommand, "cmd-native")}
                className="text-muted-foreground hover:text-foreground p-1 shrink-0"
                title="Copy command"
              >
                {copiedId === "cmd-native" ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
              </button>
            </div>

            {/* Windows PowerShell */}
            <div className="rounded-xl border border-border/40 bg-background/80 p-3 flex items-center justify-between font-mono text-xs">
              <div>
                <span className="text-muted-foreground select-none"># PowerShell Script: </span>
                <span className="text-blue-400 select-all">.\\start.ps1</span>
              </div>
              <button
                type="button"
                onClick={() => handleCopy(powershellCommand, "cmd-ps")}
                className="text-muted-foreground hover:text-foreground p-1"
                title="Copy command"
              >
                {copiedId === "cmd-ps" ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
              </button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Step 2: Agent SDK Integration */}
      <Card className="w-full">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-foreground text-background text-xs font-bold">
                2
              </span>
              <div>
                <CardTitle className="text-sm font-medium text-foreground">
                  Connect Your AI Agent
                </CardTitle>
                <CardDescription className="text-xs">
                  Integrate your memory enclave via lightweight Python / TypeScript SDK or cURL.
                </CardDescription>
              </div>
            </div>
            {/* Language Switcher */}
            <div className="flex items-center gap-1 bg-secondary/50 p-0.5 rounded-lg border border-border/40">
              <button
                type="button"
                onClick={() => setSdkLanguage("python")}
                className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
                  sdkLanguage === "python" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Python
              </button>
              <button
                type="button"
                onClick={() => setSdkLanguage("typescript")}
                className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
                  sdkLanguage === "typescript" ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                TypeScript
              </button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="relative rounded-xl border border-border/40 bg-background/90 p-4 font-mono text-xs overflow-x-auto">
            <button
              type="button"
              onClick={() => handleCopy(sdkLanguage === "python" ? pythonSdkSnippet : tsSdkSnippet, "sdk-code")}
              className="absolute top-3 right-3 flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground bg-secondary/70 px-2 py-1 rounded border border-border/40 transition-colors"
            >
              {copiedId === "sdk-code" ? (
                <>
                  <Check className="h-3 w-3 text-emerald-400" />
                  <span className="text-emerald-400">Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="h-3 w-3" />
                  <span>Copy</span>
                </>
              )}
            </button>
            <pre className="text-foreground/90 whitespace-pre leading-relaxed pr-12">
              {sdkLanguage === "python" ? pythonSdkSnippet : tsSdkSnippet}
            </pre>
          </div>
        </CardContent>
      </Card>

      {/* Step 3: MCP Hub & Tools */}
      <Card className="w-full">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-foreground text-background text-xs font-bold">
                3
              </span>
              <div>
                <CardTitle className="text-sm font-medium text-foreground">
                  Connect via Model Context Protocol (MCP)
                </CardTitle>
                <CardDescription className="text-xs">
                  Expose memories directly to Cursor, Claude Desktop, Windsurf, and Antigravity.
                </CardDescription>
              </div>
            </div>
            <Link
              href="/dashboard/mcp"
              className="text-xs text-emerald-400 hover:underline flex items-center gap-1"
            >
              <Bot className="h-3.5 w-3.5" />
              <span>Open MCP Hub &rarr;</span>
            </Link>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground font-sans leading-relaxed">
            Contexta supports both standard SSE (<code className="text-foreground font-mono">http://localhost:8765/sse</code>) and stdio transports for seamless one-click integration with modern AI coding assistants and agent runtimes.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

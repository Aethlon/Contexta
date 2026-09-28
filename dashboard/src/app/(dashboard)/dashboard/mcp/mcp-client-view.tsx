"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronDown,
  Clipboard,
  Eye,
  EyeOff,
  Loader2,
  Plus,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { createApiKeyAction } from "@/app/actions";

/**
 * MCP setup, reduced to two steps.
 *
 * The previous version of this page exposed a client selector, a CLI/JSON
 * toggle, a remote/local toggle, a protocol toggle, a tunnel URL field, and an
 * advanced disclosure — roughly 48 reachable state combinations for a user whose
 * actual goal is "make my agent talk to Contexta".
 *
 * Every MCP client needs exactly two things: the endpoint and a key. The wrapper
 * syntax differs; the payload does not. So this page shows one snippet at a time
 * and hides the rest behind a disclosure.
 *
 * It also stops pretending to know the key. The console can only ever see a
 * 16-character display prefix, so it mints a fresh key in place (the token is
 * returned exactly once) or accepts a pasted one.
 */

type ClientId = "claudecode" | "cursor" | "claude" | "windsurf" | "cline" | "antigravity";

const CLIENTS: { id: ClientId; name: string; file: string }[] = [
  { id: "claudecode", name: "Claude Code", file: "~/.claude.json" },
  { id: "cursor", name: "Cursor", file: ".cursor/mcp.json" },
  { id: "claude", name: "Claude Desktop", file: "claude_desktop_config.json" },
  { id: "windsurf", name: "Windsurf", file: "~/.codeium/windsurf/mcp_config.json" },
  { id: "cline", name: "Cline / Roo", file: "Settings → MCP Servers" },
  { id: "antigravity", name: "Antigravity", file: "mcp_config.json" },
];

interface ExistingKey {
  id: string;
  name: string;
  prefix: string;
  created_at?: string;
}

interface McpClientViewProps {
  apiUrl: string;
  existingKeys: ExistingKey[];
}

type VerifyState =
  | { status: "idle" }
  | { status: "testing" }
  | {
      status: "done";
      ok: boolean;
      transport: { ok: boolean; latencyMs?: number; error?: string };
      key: { ok: boolean; error?: string };
      tools?: unknown[];
    };

export function McpClientView({ apiUrl, existingKeys }: McpClientViewProps) {
  const [client, setClient] = useState<ClientId>("claudecode");
  const [apiKey, setApiKey] = useState("");
  const [revealKey, setRevealKey] = useState(false);
  const [minting, setMinting] = useState(false);
  const [mintError, setMintError] = useState<string | null>(null);
  const [justMinted, setJustMinted] = useState(false);
  const [copied, setCopied] = useState(false);
  const [verify, setVerify] = useState<VerifyState>({ status: "idle" });
  const [showJson, setShowJson] = useState(false);
  const [showTools, setShowTools] = useState(false);

  const endpoint = "http://localhost:8765/mcp";
  const hasKey = apiKey.trim().length > 0;
  const activeClient = CLIENTS.find((c) => c.id === client) ?? CLIENTS[0];

  // ── Status strip: the one-second answer to "is this working?" ────────────
  const [serverUp, setServerUp] = useState<boolean | null>(null);
  const [latency, setLatency] = useState<number | null>(null);

  const poll = useCallback(async () => {
    try {
      const res = await fetch("/api/system/mcp", { cache: "no-store" });
      const data = await res.json();
      setServerUp(Boolean(data.online));
      setLatency(data.latency_ms ?? null);
    } catch {
      setServerUp(false);
    }
  }, []);

  useEffect(() => {
    void poll();
    const t = setInterval(poll, 10_000);
    return () => clearInterval(t);
  }, [poll]);

  // ── Step 1: get a key ──────────────────────────────────────────────────
  const mintKey = async () => {
    setMinting(true);
    setMintError(null);
    try {
      const fd = new FormData();
      fd.set("name", "mcp-agent");
      fd.set("scopes", "read,write");
      const res = await createApiKeyAction(fd);
      const data = (res as { data?: { token?: string } }).data;
      const token = data?.token;
      if (token) {
        setApiKey(token);
        setJustMinted(true);
        setRevealKey(true);
        setVerify({ status: "idle" });
      } else {
        const err = (res as { error?: string }).error;
        setMintError(err ?? "The API did not return a token.");
      }
    } catch {
      setMintError("Could not reach the Contexta API.");
    } finally {
      setMinting(false);
    }
  };

  // ── Step 2: copy, then verify ──────────────────────────────────────────
  const snippet = useMemo(() => {
    if (!hasKey) return "";
    if (client === "claudecode") {
      return `claude mcp add contexta ${endpoint} --header "x-api-key: ${apiKey.trim()}"`;
    }
    return JSON.stringify(
      {
        mcpServers: {
          contexta: {
            url: endpoint,
            headers: { "x-api-key": apiKey.trim() },
          },
        },
      },
      null,
      2,
    );
  }, [apiKey, client, endpoint, hasKey]);

  const copy = async () => {
    await navigator.clipboard.writeText(snippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const runVerify = async () => {
    setVerify({ status: "testing" });
    try {
      const res = await fetch("/api/system/mcp/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ apiKey: apiKey.trim() }),
      });
      const data = await res.json();
      setVerify({ status: "done", ...data });
    } catch {
      setVerify({
        status: "done",
        ok: false,
        transport: { ok: false, error: "Could not reach the console backend." },
        key: { ok: false, error: "Could not reach the console backend." },
      });
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="mx-auto max-w-3xl space-y-8">
      {/* Title */}
      <header>
        <h1 className="nb-page-title">Connect an agent</h1>
        <p className="nb-page-subtitle">
          Two steps. Create a key, then run one command in your agent.
        </p>
      </header>

      {/* Live status */}
      <div className="nb-card flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3 text-[13px]">
        <span className="flex items-center gap-2">
          {serverUp === null ? (
            <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
          ) : serverUp ? (
            <CheckCircle2 className="size-3.5" style={{ color: "var(--accent-green)" }} />
          ) : (
            <XCircle className="size-3.5" style={{ color: "var(--destructive)" }} />
          )}
          <span className="text-muted-foreground">MCP server</span>
          <span className="font-medium">
            {serverUp === null ? "checking…" : serverUp ? `ready · ${latency ?? "?"}ms` : "offline"}
          </span>
        </span>
        <span className="flex items-center gap-2">
          {hasKey ? (
            <CheckCircle2 className="size-3.5" style={{ color: "var(--accent-green)" }} />
          ) : (
            <span className="size-3.5 rounded-full border border-dashed border-[color:var(--input)]" />
          )}
          <span className="text-muted-foreground">API key</span>
          <span className="font-medium">{hasKey ? "in hand" : "not set"}</span>
        </span>
        {!serverUp && (
          <span className="text-muted-foreground">
            Start it with <code className="nb-code">docker compose up -d mcp</code>
          </span>
        )}
      </div>

      {/* STEP 1 */}
      <section className="space-y-4">
        <StepBadge n={1} title="Get an API key" />
        <p className="-mt-2 text-[13px] text-muted-foreground">
          Keys are stored as a hash and shown once. If you already have one, paste it below
          instead.
        </p>

        {justMinted && apiKey ? (
          <div
            className="rounded-lg border p-4"
            style={{
              borderColor: "color-mix(in srgb, var(--accent-green) 35%, transparent)",
              background: "color-mix(in srgb, var(--accent-green) 7%, transparent)",
            }}
          >
            <p className="mb-2 flex items-center gap-1.5 text-[13px] font-medium">
              <Check className="size-4" />
              Key created — copy it now, it will not be shown again
            </p>
            <div className="flex items-center gap-2">
              <code className="nb-code flex-1 truncate select-all">
                {revealKey ? apiKey : apiKey.slice(0, 12) + "…".repeat(6)}
              </code>
              <button
                type="button"
                onClick={() => setRevealKey((v) => !v)}
                className="nb-btn nb-btn-ghost"
                aria-label={revealKey ? "Hide key" : "Reveal key"}
              >
                {revealKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
              <button
                type="button"
                onClick={async () => {
                  await navigator.clipboard.writeText(apiKey);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1800);
                }}
                className="nb-btn nb-btn-secondary"
              >
                {copied ? <Check className="size-4" /> : <Clipboard className="size-4" />}
                {copied ? "Copied" : "Copy key"}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={mintKey}
                disabled={minting}
                className="nb-btn nb-btn-primary"
              >
                {minting ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Plus className="size-4" strokeWidth={2} />
                )}
                Create an MCP key
              </button>
              {existingKeys.length > 0 && (
                <span className="text-[13px] text-muted-foreground">
                  {existingKeys.length} key{existingKeys.length > 1 ? "s" : ""} already exist —
                  those are shown as prefixes only, so mint a new one to copy the secret.
                </span>
              )}
            </div>
            {mintError && (
              <p className="flex items-center gap-1.5 text-[13px]" style={{ color: "var(--destructive)" }}>
                <AlertCircle className="size-4" /> {mintError}
              </p>
            )}

            <div className="flex items-center gap-3">
              <span className="h-px flex-1 bg-[color:var(--border)]" />
              <span className="text-xs text-muted-foreground">or paste an existing key</span>
              <span className="h-px flex-1 bg-[color:var(--border)]" />
            </div>

            <input
              type="password"
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value);
                setJustMinted(false);
                setVerify({ status: "idle" });
              }}
              placeholder="mk_live_…"
              className="nb-input font-mono"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
        )}
      </section>

      {/* STEP 2 */}
      <section className="space-y-4">
        <StepBadge n={2} title="Run it in your agent" />
        <p className="-mt-2 text-[13px] text-muted-foreground">
          Pick your agent, copy the snippet, restart it.
        </p>

        <div className="flex flex-wrap gap-1.5">
          {CLIENTS.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setClient(c.id)}
              className={`nb-btn ${client === c.id ? "nb-btn-secondary" : "nb-btn-ghost"}`}
            >
              {c.name}
            </button>
          ))}
        </div>

        {hasKey ? (
          <>
            <div className="rounded-lg border border-border bg-card">
              <div className="flex items-center justify-between border-b border-border px-3 py-2">
                <span className="text-xs text-muted-foreground">
                  {client === "claudecode" ? "Terminal" : `→ ${activeClient.file}`}
                </span>
                <button type="button" onClick={copy} className="nb-btn nb-btn-ghost">
                  {copied ? <Check className="size-4" /> : <Clipboard className="size-4" />}
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
              <pre className="overflow-x-auto px-3 py-3 font-mono text-xs leading-relaxed">
                {snippet}
              </pre>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={runVerify}
                disabled={verify.status === "testing"}
                className="nb-btn nb-btn-secondary"
              >
                {verify.status === "testing" ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <RefreshCw className="size-4" />
                )}
                Test connection
              </button>
              <span className="text-[13px] text-muted-foreground">
                Verifies the server handshake and that this key is accepted.
              </span>
            </div>

            {verify.status === "done" && <VerifyResult verify={verify} endpoint={endpoint} />}
          </>
        ) : (
          <p className="rounded-lg border border-dashed border-[color:var(--input)] px-4 py-6 text-center text-[13px] text-muted-foreground">
            Step 1 first — the snippet needs your key.
          </p>
        )}
      </section>

      {/* Disclosures */}
      <section className="space-y-2 border-t border-border pt-6">
        <Disclosure summary="What these tools do" open={showTools} onToggle={setShowTools}>
          <dl className="space-y-3 text-[13px]">
            <Tool
              name="remember"
              sig="content: string, user_id: string, title?: string"
              body="Store something worth keeping. It is redacted on the way in, so keys and tokens never reach storage."
            />
            <Tool
              name="recall"
              sig="query: string, user_id: string, focus?: string"
              body="Fuse dense, lexical and graph channels, then rerank. Only currently-true facts come back."
            />
            <Tool
              name="forget"
              sig="memory_id: string, reason?: string"
              body="Retire a memory. History is preserved; it just stops being retrievable."
            />
          </dl>
        </Disclosure>

        <Disclosure summary="Running Contexta somewhere else" open={showJson} onToggle={setShowJson}>
          <div className="space-y-3 text-[13px] text-muted-foreground">
            <p>
              The snippet above works for every client that accepts a remote HTTP MCP server. If
              yours needs a raw JSON file instead, it is the same payload:
            </p>
            <pre className="overflow-x-auto rounded-lg border border-border bg-card px-3 py-3 font-mono text-xs">
{`{
  "mcpServers": {
    "contexta": {
      "url": "${endpoint}",
      "headers": { "x-api-key": "<your key>" }
    }
  }
}`}
            </pre>
            <p>
              On another machine, set <code className="nb-code">CONTEXTA_MCP_URL</code> on the
              console and expose port 8765 — or terminate TLS in front of it. Never expose this
              port unauthenticated.
            </p>
          </div>
        </Disclosure>
      </section>
    </div>
  );
}

function StepBadge({ n, title }: { n: number; title: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        className="flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
        style={{ background: "var(--primary)", color: "var(--primary-foreground)" }}
      >
        {n}
      </span>
      <h2 className="text-sm font-semibold text-foreground">{title}</h2>
    </div>
  );
}

function VerifyResult({
  verify,
  endpoint,
}: {
  verify: Extract<VerifyState, { status: "done" }>;
  endpoint: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-2 rounded-lg border border-border bg-card px-4 py-3"
    >
      <Row
        ok={verify.transport.ok}
        label="MCP transport"
        detail={
          verify.transport.ok
            ? `Handshake completed on ${endpoint} in ${verify.transport.latencyMs ?? "?"}ms.`
            : verify.transport.error
        }
      />
      <Row
        ok={verify.key.ok}
        label="API key"
        detail={verify.key.ok ? "Accepted, and the tenant resolved." : verify.key.error}
      />
      {verify.ok && (
        <p className="pt-1 text-[13px] font-medium" style={{ color: "var(--accent-green)" }}>
          Ready — restart your agent and ask it to remember something.
        </p>
      )}
    </motion.div>
  );
}

function Row({ ok, label, detail }: { ok: boolean; label: string; detail?: string }) {
  return (
    <div className="flex items-start gap-2.5 text-[13px]">
      {ok ? (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0" style={{ color: "var(--accent-green)" }} />
      ) : (
        <AlertCircle className="mt-0.5 size-4 shrink-0" style={{ color: "var(--destructive)" }} />
      )}
      <div className="min-w-0">
        <span className="font-medium text-foreground">{label}</span>
        {detail && <p className="text-muted-foreground">{detail}</p>}
      </div>
    </div>
  );
}

function Tool({ name, sig, body }: { name: string; sig: string; body: string }) {
  return (
    <div>
      <dt className="flex flex-wrap items-baseline gap-2">
        <code className="nb-code">{name}</code>
        <span className="text-xs text-muted-foreground">({sig})</span>
      </dt>
      <dd className="mt-1 text-muted-foreground">{body}</dd>
    </div>
  );
}

function Disclosure({
  summary,
  children,
  open,
  onToggle,
}: {
  summary: string;
  children: React.ReactNode;
  open: boolean;
  onToggle: (v: boolean) => void;
}) {
  return (
    <div>
      <button
        type="button"
        onClick={() => onToggle(!open)}
        className="flex w-full items-center gap-2 py-2 text-[13px] font-medium text-foreground transition-colors hover:text-[color:var(--accent-blue)]"
        aria-expanded={open}
      >
        <ChevronDown
          className={`size-4 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
          strokeWidth={1.75}
        />
        {summary}
      </button>
      {open && <div className="pb-4 pl-6">{children}</div>}
    </div>
  );
}

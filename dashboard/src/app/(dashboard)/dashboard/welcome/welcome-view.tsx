"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Loader2,
  Rocket,
  Terminal,
} from "lucide-react";
import { ingestObservationAction } from "@/app/actions";

/**
 * First-run flow.
 *
 * v1.5 deleted the previous `/onboarding` chat (992 lines) and its form, leaving
 * no first-run experience at all. This replaces it with three steps that reflect
 * the tenant's *real* state rather than a scripted tour:
 *
 *   1. the engine is up
 *   2. an API key exists
 *   3. at least one memory has been extracted
 *
 * Each step is derived from the database, so a returning user who already has
 * keys and memories is simply told they are done rather than walked through
 * setup they have already completed.
 */

const EXAMPLES = [
  "I moved from New York to London last month.",
  "My Postgres server runs on port 5432 and I use Qwen3 locally.",
  "I prefer dark roast coffee and I am allergic to shellfish.",
];

export function WelcomeView({
  keyCount,
  memoryCount,
}: {
  keyCount: number;
  memoryCount: number;
}) {
  const router = useRouter();
  const [serverUp, setServerUp] = useState<boolean | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const poll = useCallback(async () => {
    try {
      const res = await fetch("/api/system/engine", { cache: "no-store" });
      const data = await res.json();
      setServerUp(Boolean(data?.online));
      if (typeof data?.latency_ms === "number") setLatency(data.latency_ms);
    } catch {
      setServerUp(false);
    }
  }, []);

  useEffect(() => {
    void poll();
    const t = setInterval(poll, 10_000);
    return () => clearInterval(t);
  }, [poll]);

  const hasKey = keyCount > 0;
  const hasMemory = memoryCount > 0;
  const engineUp = serverUp !== false;
  const allDone = hasKey && hasMemory && engineUp;

  const send = async () => {
    const content = text.trim();
    if (!content) return;
    setSending(true);
    setError(null);
    try {
      const res = await ingestObservationAction({
        messages: [{ role: "user", content }],
      });
      if (res && "error" in res && res.error) {
        setError(res.error);
      } else {
        setSent(true);
        setText("");
        // Extraction is async, so give it a moment before we show the result.
        setTimeout(() => router.refresh(), 6000);
      }
    } catch {
      setError("Could not reach the Contexta API.");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-10">
      <header>
        <h1 className="nb-page-title">Welcome to Contexta</h1>
        <p className="nb-page-subtitle">
          Three things to get working. Each one below reflects your actual state, so you can stop
          as soon as you are done.
        </p>
      </header>

      {allDone && (
        <div
          className="rounded-lg border p-4"
          style={{
            borderColor: "color-mix(in srgb, var(--accent-green) 35%, transparent)",
            background: "color-mix(in srgb, var(--accent-green) 7%, transparent)",
          }}
        >
          <p className="flex items-center gap-2 text-sm font-medium">
            <CheckCircle2 className="size-4" />
            You are set up. {memoryCount} memor{memoryCount === 1 ? "y" : "ies"} and {keyCount} key
            {keyCount === 1 ? "" : "s"} on this tenant.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link href="/dashboard/memories" className="nb-btn nb-btn-secondary">
              Browse memories
            </Link>
            <Link href="/dashboard" className="nb-btn nb-btn-ghost">
              Go to overview
            </Link>
          </div>
        </div>
      )}

      {/* Step 1 */}
      <Step
        n={1}
        title="The engine is running"
        done={engineUp}
        doneLabel="Local engine responding"
        detail="Contexta runs entirely on your machine â€” local Qwen3 models, your own database, no cloud keys."
      >
        {serverUp === null ? (
          <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Checkingâ€¦
          </p>
        ) : engineUp ? (
          <p className="text-[13px] text-muted-foreground">
            Everything is local — nothing you send here leaves this machine (engine responded in {latency ?? "?"}ms).
          </p>
        ) : (
          <div className="space-y-2">
            <p className="text-[13px] text-muted-foreground">
              The engine is not answering. Start the stack and reload this page.
            </p>
            <code className="nb-code block">docker compose up -d</code>
          </div>
        )}
      </Step>

      {/* Step 2 */}
      <Step
        n={2}
        title="Create an API key"
        done={hasKey}
        doneLabel={`${keyCount} key${keyCount === 1 ? "" : "s"} on this tenant`}
        detail="Your agent authenticates with a key. The console can create one for you in a single click â€” no SQL, no hashing by hand."
      >
        <Link href="/dashboard/mcp" className="nb-btn nb-btn-primary">
          <Terminal className="size-4" strokeWidth={1.75} />
          Create a key and connect an agent
          <ArrowRight className="size-4" />
        </Link>
        <p className="mt-2 text-[13px] text-muted-foreground">
          That page is also where you verify the connection afterwards.
        </p>
      </Step>

      {/* Step 3 */}
      <Step
        n={3}
        title="Store your first memory"
        done={hasMemory}
        doneLabel={`${memoryCount} memor${memoryCount === 1 ? "y" : "ies"} extracted`}
        detail="Type something and watch it become a typed, linkable fact. This is the same path your agent will use."
      >
        {hasMemory && !sent ? (
          <p className="text-[13px] text-muted-foreground">
            You already have memories â€” nothing to do here.
          </p>
        ) : sent ? (
          <div className="space-y-2">
            <p
              className="flex items-center gap-2 text-[13px] font-medium"
              style={{ color: "var(--accent-green)" }}
            >
              <CheckCircle2 className="size-4" /> Accepted â€” extraction is running.
            </p>
            <p className="text-[13px] text-muted-foreground">
              Give it a few seconds, then{" "}
              <Link href="/dashboard/memories" className="underline underline-offset-2">
                see what it extracted
              </Link>
              .
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={3}
              placeholder="e.g. I moved from New York to London last month."
              className="w-full resize-y rounded-md border bg-card px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-[color:var(--text-tertiary)] focus:border-[color:var(--accent-blue)]"
              style={{ borderColor: "var(--input)" }}
            />
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={send}
                disabled={sending || !text.trim()}
                className="nb-btn nb-btn-primary"
              >
                {sending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Rocket className="size-4" strokeWidth={1.75} />
                )}
                {sending ? "Sendingâ€¦" : "Send it"}
              </button>
              <span className="text-xs text-muted-foreground">try:</span>
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => setText(ex)}
                  className="rounded-full border border-[color:var(--input)] px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  {ex.length > 34 ? ex.slice(0, 34) + "â€¦" : ex}
                </button>
              ))}
            </div>
            {error && <p className="text-[13px]" style={{ color: "var(--destructive)" }}>{error}</p>}
          </div>
        )}
      </Step>
    </div>
  );
}

function Step({
  n,
  title,
  detail,
  done,
  doneLabel,
  children,
}: {
  n: number;
  title: string;
  detail: string;
  done: boolean;
  doneLabel: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
          style={{
            background: done ? "var(--accent-green)" : "var(--primary)",
            color: done ? "#fff" : "var(--primary-foreground)",
          }}
        >
          {done ? <Check className="size-3.5" strokeWidth={3} /> : n}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-2">
            <h2 className="text-sm font-semibold text-foreground">{title}</h2>
            {done && (
              <span
                className="text-[13px] font-medium"
                style={{ color: "var(--accent-green)" }}
              >
                {doneLabel}
              </span>
            )}
          </div>
          <p className="mt-1 text-[13px] text-muted-foreground">{detail}</p>
        </div>
      </div>
      <div className="pl-9">{!done && children}</div>
    </section>
  );
}

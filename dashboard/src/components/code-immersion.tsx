"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

type Lang = "python" | "typescript" | "curl";

const SNIPPETS: Record<Lang, string> = {
  python: `from contexta import ContextaClient

client = ContextaClient(api_key="ctx_live_9182390f")

# Ingest multi-turn conversational observations
client.observe(
    user_id="usr_9102",
    messages=[
        {"role": "user", "content": "I prefer Rust over Go for systems code, and deploy on Tokyo AWS."}
    ]
)

# Sub-180ms hybrid vector + graph triple retrieval
memory = client.retrieve(
    user_id="usr_9102",
    query="What systems language and cloud region does the user use?"
)
print(memory.ranked_facts)
# => [Fact(key="language_preference", value="Rust", confidence=0.99),
#     Fact(key="aws_region", value="ap-northeast-1 (Tokyo)", confidence=0.97)]`,
  typescript: `import { ContextaClient } from "@contexta/sdk";

const client = new ContextaClient({
  apiKey: process.env.CONTEXTA_API_KEY!,
});

// Stream observations into tenant memory enclave
await client.observe({
  userId: "usr_9102",
  messages: [
    { role: "user", content: "I prefer Rust over Go for systems code, and deploy on Tokyo AWS." },
  ],
});

// Hybrid dense cosine + BM25 + graph recall
const { rankedFacts } = await client.retrieve({
  userId: "usr_9102",
  query: "What systems language and cloud region does the user use?",
});
console.log(rankedFacts);`,
  curl: `curl -X POST https://api.contexta.ai/v1/observations \\
  -H "Authorization: Bearer $CONTEXTA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "user_id": "usr_9102",
    "messages": [
      {"role": "user", "content": "I prefer Rust over Go and use Neovim for systems code."}
    ]
  }'`,
};

const TRY_RESULTS: Record<string, string> = {
  "rust": `[Fact(language_preference=Rust, conf=0.99), Fact(aws_region=ap-northeast-1, conf=0.97)]`,
  "tokyo": `[Fact(current_office=Tokyo HQ, conf=0.99), Fact(timezone=Asia/Tokyo, conf=0.99)]`,
  "default": `[Fact(primary_language=Rust, conf=0.98), Fact(editor=Neovim, conf=0.96)]`,
};

export function CodeImmersion() {
  const [tab, setTab] = useState<Lang>("python");
  const [copied, setCopied] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [query, setQuery] = useState("What language does the user prefer?");
  const [result, setResult] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(SNIPPETS[tab]);
    } catch {
      /* ignore */
    }
    setCopied(true);
    setToast("Snippet copied to clipboard");
    setTimeout(() => {
      setCopied(false);
      setToast(null);
    }, 1800);
  };

  const runTry = () => {
    if (running) return;
    setRunning(true);
    setResult(null);
    const q = query.toLowerCase();
    const key = q.includes("rust") ? "rust" : q.includes("tokyo") || q.includes("region") || q.includes("office") ? "tokyo" : "default";
    setTimeout(() => {
      setResult(TRY_RESULTS[key]);
      setRunning(false);
    }, 650);
  };

  return (
    <section id="integration" className="py-24 sm:py-32 border-t border-border">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-start">
        <motion.div
          className="lg:col-span-5 space-y-6 lg:sticky lg:top-28"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.7 }}
        >
          <div className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-blue-400">
            Drop-in integration
          </div>
          <h2 className="text-title text-3xl sm:text-4xl tracking-tight text-foreground">
            Three lines of code to connect persistent memory.
          </h2>
          <p className="text-sm font-light text-[#6B7280] leading-relaxed">
            Plug Contexta into LangChain, LlamaIndex, Cursor, or FastAPI with zero changes
            to your agent prompt loops. Simulated locally â€” no key required.
          </p>
          <div className="flex items-center gap-2 bg-accent p-1 rounded-full w-fit" role="tablist" aria-label="Language">
            {(["python", "typescript", "curl"] as Lang[]).map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                className={`px-4 py-1.5 rounded-full text-xs font-mono uppercase tracking-wider transition-all ${
                  tab === t ? "bg-blue-500/20 text-blue-300" : "text-[#6B7280] hover:text-foreground"
                }`}
              >
                {t === "typescript" ? "ts" : t}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            {[
              { v: "3 lines", k: "to first recall" },
              { v: "<14ms", k: "ingest overhead" },
              { v: "MIT", k: "self-hosted" },
            ].map((s) => (
              <div key={s.k} className="rounded-lg bg-accent p-3 shadow-elev-1">
                <div className="text-lg font-light text-foreground">{s.v}</div>
                <div className="text-[10px] font-mono uppercase tracking-widest text-[#3D4450]">{s.k}</div>
              </div>
            ))}
          </div>
        </motion.div>

        <motion.div
          className="lg:col-span-7 relative p-6 sm:p-8 rounded-lg bg-[#09090C] shadow-elev-3  overflow-hidden"
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.8 }}
        >
          <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-blue-500/50 to-transparent" />
          <button
            onClick={copy}
            className="absolute top-4 right-4 px-3 py-1.5 rounded-full bg-accent hover:bg-accent text-[11px] font-mono text-[#6B7280] hover:text-foreground transition-all"
            aria-label="Copy code snippet"
          >
            {copied ? "copied âœ“" : "copy"}
          </button>

          <AnimatePresence mode="wait">
            <motion.pre
              key={tab}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
              className="overflow-x-auto font-mono text-xs text-[#D1D5DB] leading-relaxed pr-16 min-h-[280px]"
              tabIndex={0}
              aria-label={`${tab} quickstart snippet`}
            >
              <code>{SNIPPETS[tab]}</code>
            </motion.pre>
          </AnimatePresence>

          <div className="mt-6 pt-5 border-t border-border space-y-3">
            <div className="text-[11px] font-mono uppercase tracking-widest text-[#3D4450]">Try it â€” simulated recall</div>
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && runTry()}
                className="flex-1 rounded-lg bg-black/40 px-4 py-2.5 text-xs font-mono text-foreground outline-none focus:ring-2 focus:ring-blue-500/40 placeholder:text-[#3D4450]"
                placeholder="Ask about language, region, officeâ€¦"
                aria-label="Test query"
              />
              <button
                onClick={runTry}
                disabled={running}
                className="px-5 py-2.5 rounded-full bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-xs font-mono text-foreground transition-all"
              >
                {running ? "runningâ€¦" : "Run â–¸"}
              </button>
            </div>
            <div className="min-h-[44px] rounded-lg bg-black/50 px-4 py-3 font-mono text-[11px] leading-relaxed" aria-live="polite">
              {running ? (
                <span className="text-[#3D4450] animate-pulse">â– fusing vector + BM25 + graphâ€¦</span>
              ) : result ? (
                <span className="tone-green">{result}</span>
              ) : (
                <span className="text-[#3D4450]">result appears here â€¢ try â€œrustâ€ or â€œtokyoâ€</span>
              )}
            </div>
          </div>

          <AnimatePresence>
            {toast && (
              <motion.div
                className="toast"
                initial={{ opacity: 0, x: 24 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 24 }}
                role="status"
              >
                <span className="w-2 h-2 rounded-full dot dot-green" />
                {toast}
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </div>
    </section>
  );
}

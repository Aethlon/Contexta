"use client";

import React, { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { PlusCircle, X, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import { ingestObservationAction } from "@/app/actions";

export function IngestObservationModal() {
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [isPending, startTransition] = useTransition();

  const [userMessage, setUserMessage] = useState("");
  const [assistantMessage, setAssistantMessage] = useState("");
  const [userId, setUserId] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!userMessage.trim()) {
      setErrorMsg("Please enter a user statement or message.");
      return;
    }

    setErrorMsg(null);
    setSuccessMsg(null);

    const messages = [
      { role: "user", content: userMessage.trim() },
    ];
    if (assistantMessage.trim()) {
      messages.push({ role: "assistant", content: assistantMessage.trim() });
    }

    startTransition(async () => {
      const res = await ingestObservationAction({
        userId: userId.trim() || undefined,
        messages,
      });

      if (res?.error) {
        setErrorMsg(res.error);
      } else {
        setSuccessMsg("Observation accepted! Extraction job scheduled.");
        setUserMessage("");
        setAssistantMessage("");
        router.refresh();
        setTimeout(() => {
          setIsOpen(false);
          setSuccessMsg(null);
        }, 1200);
      }
    });
  };

  return (
    <>
      <button
        onClick={() => {
          setIsOpen(true);
          setErrorMsg(null);
          setSuccessMsg(null);
        }}
        className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-graphite)]/40 bg-[var(--color-ash)] px-3 py-1.5 font-mono text-xs text-[var(--color-ghost)] transition-colors hover:border-[var(--color-graphite)] hover:bg-[var(--color-charcoal)]"
      >
        <PlusCircle className="size-3.5 text-blue-400" />
        <span>Ingest Observation</span>
      </button>

      {isOpen && (
        <div
          onClick={(e) => {
            if (e.target === e.currentTarget) setIsOpen(false);
          }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in"
        >
          <div className="relative w-full max-w-lg rounded-2xl border border-[var(--color-graphite)]/60 bg-[var(--color-abyss)] p-6 shadow-2xl space-y-5">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-[var(--color-graphite)]/30 pb-4">
              <div>
                <h3 className="text-base font-normal text-[var(--color-ghost)]">
                  Ingest Test Observation
                </h3>
                <p className="text-xs font-light text-[var(--color-smoke)]">
                  Submit a conversation turn to extract atomic memories into Contexta.
                </p>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="rounded-lg p-1 text-[var(--color-smoke)] hover:text-[var(--color-ghost)] transition-colors"
              >
                <X className="size-4" />
              </button>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="block text-[11px] font-mono uppercase tracking-wider text-[var(--color-smoke)]">
                  User Statement <span className="text-red-400">*</span>
                </label>
                <textarea
                  rows={3}
                  value={userMessage}
                  onChange={(e) => setUserMessage(e.target.value)}
                  placeholder="e.g., I prefer Postgres over Mongo for relational data and deployed v2.4 to us-east-1."
                  className="w-full rounded-xl border border-[var(--color-graphite)]/40 bg-[var(--color-ash)] px-3 py-2 text-xs font-mono text-[var(--color-ghost)] placeholder:text-[var(--color-smoke)]/60 focus:outline-none focus:border-blue-500/50 resize-none"
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-[11px] font-mono uppercase tracking-wider text-[var(--color-smoke)]">
                  Assistant Response <span className="text-gray-500">(optional)</span>
                </label>
                <input
                  type="text"
                  value={assistantMessage}
                  onChange={(e) => setAssistantMessage(e.target.value)}
                  placeholder="e.g., Got it, I'll keep your PostgreSQL preference in mind."
                  className="w-full rounded-xl border border-[var(--color-graphite)]/40 bg-[var(--color-ash)] px-3 py-2 text-xs font-mono text-[var(--color-ghost)] placeholder:text-[var(--color-smoke)]/60 focus:outline-none focus:border-blue-500/50"
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-[11px] font-mono uppercase tracking-wider text-[var(--color-smoke)]">
                  Custom User ID <span className="text-gray-500">(optional, defaults to current session)</span>
                </label>
                <input
                  type="text"
                  value={userId}
                  onChange={(e) => setUserId(e.target.value)}
                  placeholder="UUID or leave blank"
                  className="w-full rounded-xl border border-[var(--color-graphite)]/40 bg-[var(--color-ash)] px-3 py-2 text-xs font-mono text-[var(--color-ghost)] placeholder:text-[var(--color-smoke)]/60 focus:outline-none focus:border-blue-500/50"
                />
              </div>

              {errorMsg && (
                <div className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
                  <AlertCircle className="size-4 shrink-0" />
                  <span>{errorMsg}</span>
                </div>
              )}

              {successMsg && (
                <div className="flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
                  <CheckCircle2 className="size-4 shrink-0" />
                  <span>{successMsg}</span>
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  className="rounded-lg px-3 py-1.5 text-xs font-mono text-[var(--color-smoke)] hover:text-[var(--color-ghost)] transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isPending}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-mono font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {isPending && <Loader2 className="size-3 animate-spin" />}
                  <span>{isPending ? "Ingesting..." : "Submit Observation"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}

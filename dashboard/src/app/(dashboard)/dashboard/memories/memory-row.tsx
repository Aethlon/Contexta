"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, GitBranch, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { TableCell, TableRow } from "@/components/ui/table";
import { motion } from "framer-motion";
import { getMemoryDetailAction } from "@/app/actions";

type Fact = {
  subject?: string;
  predicate?: string;
  object?: string;
  context?: string;
  status?: string;
  polarity?: string;
  confidence?: number;
  temporal?: { basis?: string; precision?: string; observed_at?: string | null };
  temporal_source?: string;
};

/**
 * The extractor's subject/predicate/object triple.
 *
 * Two shapes exist in the wild and both are read: nested under a `fact` key, and
 * flattened directly into `structured_data` (which is what the current extractor
 * actually writes).
 */
function readFact(structured: Record<string, unknown> | null | undefined): Fact | null {
  if (!structured || typeof structured !== "object") return null;
  const nested = (structured as { fact?: Fact }).fact;
  const source =
    nested && typeof nested === "object" && (nested.subject || nested.object)
      ? nested
      : (structured as Fact);
  return source.subject || source.object || source.predicate ? source : null;
}

type LineageEntry = {
  id: string;
  content: string;
  importance: number;
  valid_from: string | null;
  valid_to: string | null;
  superseded_by_id: string | null;
};

type MemoryDetail = {
  id: string;
  user_id: string;
  organization_id: string;
  content: string;
  structured_data: Record<string, unknown> | null;
  source_type: string;
  utility_score: number;
  memory_state: string;
  valid_from: string | null;
  valid_to: string | null;
  created_at: string | null;
  last_accessed_at: string | null;
};

export function MemoryRow({ memory }: { memory: any }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<{
    detail: MemoryDetail;
    lineage: LineageEntry[] | null;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const state = memory.memory_state ?? memory.state ?? "active";

  useEffect(() => {
    if (!open || detail || loading) return;
    let cancelled = false;
    setLoading(true);
    getMemoryDetailAction(memory.id).then((result) => {
      if (cancelled) return;
      setLoading(false);
      if (result) setDetail(result);
    });
    return () => {
      cancelled = true;
    };
  }, [open, detail, loading, memory.id]);

  const fact: Fact | null = detail ? readFact(detail.detail.structured_data) : null;

  const superseded = Boolean(detail?.detail.valid_to);

  return (
    <>
      <TableRow
        className="cursor-pointer hover:bg-[var(--muted)]/30 transition-colors duration-200"
        onClick={() => setOpen(!open)}
      >
        <TableCell className="w-[50px]">
          {open ? (
            <ChevronUp className="h-4 w-4 text-[var(--text-secondary)]" strokeWidth={1.2} />
          ) : (
            <ChevronDown className="h-4 w-4 text-[var(--text-secondary)]" strokeWidth={1.2} />
          )}
        </TableCell>
        <TableCell className="font-normal text-[var(--foreground)]">
          {memory.title ?? "Untitled"}
        </TableCell>
        <TableCell className="text-[var(--text-secondary)] font-light text-xs">
          {memory.memory_type ?? "—"}
        </TableCell>
        <TableCell>
          <Badge className="lowercase">{state}</Badge>
        </TableCell>
        <TableCell className="text-right tabular-nums text-[var(--text-secondary)] font-light">
          {typeof memory.importance === "number" ? memory.importance.toFixed(2) : "—"}
        </TableCell>
        <TableCell className="text-right tabular-nums text-[var(--text-secondary)] font-light">
          {typeof memory.confidence === "number" ? memory.confidence.toFixed(2) : "—"}
        </TableCell>
      </TableRow>
      {open && (
        <TableRow>
          <TableCell colSpan={6} className="bg-[var(--card)]/40 p-6 border-b border-[var(--border)]/30">
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-4 text-sm font-light text-[var(--foreground)]"
            >
              {loading ? (
                <p className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
                  <Loader2 className="size-3 animate-spin" /> Loading record…
                </p>
              ) : null}

              {detail ? (
                <>
                  <p className="whitespace-pre-wrap leading-relaxed text-[var(--foreground)]/95">
                    {detail.detail.content || "No content"}
                  </p>

                  {/* Fact triple written by the extractor */}
                  <div className="rounded-lg border border-[var(--border)]/30 bg-[var(--background)] p-4">
                    <p className="mb-2 text-[10px] font-mono tracking-widest uppercase text-[var(--text-secondary)]">
                      fact triple (subject / predicate / object)
                    </p>
                    {fact ? (
                      <div className="space-y-2 font-mono text-xs">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded border border-[var(--border)]/40 px-2 py-1">
                            {fact.subject ?? "—"}
                          </span>
                          <span className="text-[var(--text-secondary)]">
                            {fact.predicate ?? "—"}
                          </span>
                          <span className="rounded border border-[var(--border)]/40 px-2 py-1">
                            {fact.object ?? "—"}
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-3 text-[10px] text-[var(--text-secondary)]">
                          {fact.status ? <span>status: {fact.status}</span> : null}
                          {fact.polarity ? (
                            <span>polarity: {fact.polarity}</span>
                          ) : null}
                          {typeof fact.confidence === "number" ? (
                            <span>triple confidence: {fact.confidence.toFixed(2)}</span>
                          ) : null}
                          {fact.context ? <span>context: {fact.context}</span> : null}
                          {fact.temporal?.basis ? (
                            <span>temporal basis: {fact.temporal.basis}</span>
                          ) : null}
                          {fact.temporal_source ? (
                            <span>temporal source: {fact.temporal_source}</span>
                          ) : null}
                        </div>
                      </div>
                    ) : (
                      <p className="font-mono text-xs text-[var(--text-secondary)]">
                        This record carries no fact triple. Rows written before the
                        triple existed, or whose extractor omitted it, fall back to
                        a text-hash fact key.
                      </p>
                    )}
                  </div>

                  {/* Validity window + supersession lineage */}
                  <div className="rounded-lg border border-[var(--border)]/30 bg-[var(--background)] p-4">
                    <p className="mb-2 flex items-center gap-1.5 text-[10px] font-mono tracking-widest uppercase text-[var(--text-secondary)]">
                      <GitBranch className="size-3" />
                      Validity &amp; supersession
                    </p>
                    <div className="space-y-1.5 font-mono text-xs text-[var(--text-secondary)]">
                      <p>
                        valid_from:{" "}
                        <span className="text-[var(--foreground)]">
                          {detail.detail.valid_from ?? "—"}
                        </span>
                      </p>
                      <p>
                        valid_to:{" "}
                        <span
                          className={superseded ? "tone-amber" : "text-[var(--foreground)]"}
                        >
                          {detail.detail.valid_to ?? "— (still current)"}
                        </span>
                      </p>
                      <p>
                        state: <span className="text-[var(--foreground)]">{detail.detail.memory_state}</span>
                        {superseded ? " · this row has been superseded" : ""}
                      </p>
                    </div>

                    {detail.lineage && detail.lineage.length > 0 ? (
                      <ol className="mt-3 space-y-2 border-t border-[var(--border)]/30 pt-3">
                        {detail.lineage.map((entry) => (
                          <li key={entry.id} className="font-mono text-[11px]">
                            <span className="text-[var(--foreground)]">
                              {entry.id.slice(0, 8)}…
                            </span>{" "}
                            <span className="text-[var(--text-secondary)]">
                              {entry.valid_from ?? "?"} &rarr; {entry.valid_to ?? "current"}
                            </span>
                            {entry.superseded_by_id ? (
                              <span className="ml-1 tone-amber">
                                superseded_by {entry.superseded_by_id.slice(0, 8)}…
                              </span>
                            ) : null}
                            <p className="mt-0.5 line-clamp-2 text-[var(--text-secondary)]/80">
                              {entry.content}
                            </p>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="mt-2 font-mono text-[10px] text-[var(--text-secondary)]">
                        No MemoryVersion rows: this memory has never been revised.
                      </p>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-x-6 gap-y-1 text-[10px] font-mono tracking-wider text-[var(--text-secondary)]">
                    <span>ID: {detail.detail.id.slice(0, 8)}…</span>
                    <span>source: {detail.detail.source_type}</span>
                    <span>utility: {detail.detail.utility_score?.toFixed(2) ?? "—"}</span>
                    <span>
                      created:{" "}
                      {detail.detail.created_at
                        ? new Date(detail.detail.created_at).toLocaleString()
                        : "—"}
                    </span>
                    <span>
                      last read:{" "}
                      {detail.detail.last_accessed_at
                        ? new Date(detail.detail.last_accessed_at).toLocaleString()
                        : "never"}
                    </span>
                  </div>
                </>
              ) : loading ? null : (
                <p className="text-xs text-[var(--text-secondary)]">
                  Could not load this record.
                </p>
              )}

              {memory.tags && memory.tags.length > 0 ? (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {memory.tags.map((tag: string) => (
                    <Badge key={tag} className="text-[9px]">
                      {tag}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </motion.div>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

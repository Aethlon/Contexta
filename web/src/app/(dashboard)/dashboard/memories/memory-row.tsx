"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { TableCell, TableRow } from "@/components/ui/table";
import { motion } from "framer-motion";

export function MemoryRow({ memory }: { memory: any }) {
  const [open, setOpen] = useState(false);
  const state = memory.memory_state ?? memory.state ?? "active";

  return (
    <>
      <TableRow
        className="cursor-pointer hover:bg-[var(--color-charcoal)]/30 transition-colors duration-200"
        onClick={() => setOpen(!open)}
      >
        <TableCell className="w-[50px]">
          {open ? (
            <ChevronUp className="h-4 w-4 text-[var(--color-smoke)]" strokeWidth={1.2} />
          ) : (
            <ChevronDown className="h-4 w-4 text-[var(--color-smoke)]" strokeWidth={1.2} />
          )}
        </TableCell>
        <TableCell className="font-normal text-[var(--color-ghost)]">{memory.title ?? "Untitled"}</TableCell>
        <TableCell className="text-[var(--color-smoke)] font-light text-xs">{memory.memory_type ?? "—"}</TableCell>
        <TableCell>
          <Badge className="lowercase">{state}</Badge>
        </TableCell>
        <TableCell className="text-right tabular-nums text-[var(--color-smoke)] font-light">
          {typeof memory.importance === "number" ? memory.importance.toFixed(2) : "—"}
        </TableCell>
        <TableCell className="text-right tabular-nums text-[var(--color-smoke)] font-light">
          {typeof memory.confidence === "number" ? memory.confidence.toFixed(2) : "—"}
        </TableCell>
      </TableRow>
      {open && (
        <TableRow>
          <TableCell colSpan={6} className="bg-[var(--color-ash)]/40 p-6 border-b border-[var(--color-graphite)]/30">
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-4 text-sm font-light text-[var(--color-ghost)]"
            >
              <p className="whitespace-pre-wrap leading-relaxed text-[var(--color-ghost)]/95">{memory.content ?? "No content"}</p>
              
              {memory.structured_data && Object.keys(memory.structured_data).length > 0 && (
                <div className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-abyss)] p-4">
                  <p className="mb-2 text-[10px] font-mono tracking-widest uppercase text-[var(--color-smoke)]">Structured Data</p>
                  <pre className="font-mono text-xs text-[var(--color-smoke)] overflow-x-auto leading-relaxed">{JSON.stringify(memory.structured_data, null, 2)}</pre>
                </div>
              )}
              
              {memory.tags && memory.tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {memory.tags.map((tag: string) => (
                    <Badge key={tag} className="text-[9px]">{tag}</Badge>
                  ))}
                </div>
              )}
              
              <div className="flex gap-6 text-[10px] font-mono tracking-wider text-[var(--color-smoke)] pt-1">
                <span>ID: {memory.id?.slice(0, 8)}…</span>
                <span>Created: {memory.created_at ? new Date(memory.created_at).toLocaleString() : "—"}</span>
              </div>
            </motion.div>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

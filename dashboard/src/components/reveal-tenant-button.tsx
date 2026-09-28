"use client";

import { Rocket } from "lucide-react";
import Link from "next/link";

export const REVEAL_TENANT_EVENT = "contexta:reveal-tenant";

/**
 * Buttons that open the sidebar organization panel from anywhere in the console.
 *
 * The panel lives in the sidebar, which is server-rendered shell, so a page
 * cannot reach its open state directly. Broadcasting an event keeps the wiring in
 * one place instead of lifting the panel's state to the layout.
 */
export function RevealTenantButton({ label }: { label: string }) {
  return (
    <button
      type="button"
      onClick={() => window.dispatchEvent(new Event(REVEAL_TENANT_EVENT))}
      className="inline-flex items-center gap-1.5 rounded-md border border-red-500/40 px-2.5 py-1.5 text-xs font-medium transition-colors hover:bg-red-500/10"
    >
      <span>{label}</span>
    </button>
  );
}

export function FirstRunLink({ label }: { label: string }) {
  return (
    <Link
      href="/dashboard/welcome"
      className="inline-flex items-center gap-1.5 rounded-md border border-red-500/40 px-2.5 py-1.5 text-xs font-medium transition-colors hover:bg-red-500/10"
    >
      <Rocket className="size-3" strokeWidth={1.75} />
      <span>{label}</span>
    </Link>
  );
}

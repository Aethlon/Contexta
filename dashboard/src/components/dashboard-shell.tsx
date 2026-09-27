"use client";

import React, { useState, useEffect, useCallback } from "react";
import { DashboardSidebar } from "@/components/dashboard-sidebar";
import { ThemeToggle } from "@/components/theme-toggle";
import { EngineStatusBadge } from "@/components/engine-status-badge";
import { IngestObservationModal } from "@/components/ingest-observation-modal";
import { PanelLeft, ShieldOff } from "lucide-react";
import type { OperatorIdentity } from "@/lib/dashboard-identity";

interface DashboardShellProps {
  children: React.ReactNode;
  identity: OperatorIdentity;
}

export function DashboardShell({ children, identity }: DashboardShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const stored = localStorage.getItem("contexta_sidebar_open");
    if (stored !== null) {
      setSidebarOpen(stored === "true");
    } else if (window.innerWidth < 1024) {
      setSidebarOpen(false);
    }
  }, []);

  const toggleSidebar = useCallback(() => {
    setSidebarOpen((prev) => {
      const next = !prev;
      localStorage.setItem("contexta_sidebar_open", String(next));
      return next;
    });
  }, []);

  // Ctrl/Cmd+B toggles the sidebar, as in Notion.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleSidebar();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggleSidebar]);

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background text-foreground">
      {/* Mobile backdrop */}
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-40 md:hidden"
          style={{ background: "var(--overlay)" }}
          aria-hidden="true"
        />
      )}

      {/* Sidebar — flat surface, hairline right edge */}
      <div
        className={`fixed inset-y-0 left-0 z-50 flex flex-col transition-[width,transform] duration-200 ease-out md:static md:z-auto ${
          sidebarOpen ? "w-60 translate-x-0" : "-translate-x-full md:w-0 md:overflow-hidden"
        }`}
        style={{ background: "var(--sidebar)" }}
      >
        <div className="flex h-full w-60 flex-col border-r border-border">
          <DashboardSidebar identity={identity} />
        </div>
      </div>

      {/* Content column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-border px-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              onClick={toggleSidebar}
              title="Toggle sidebar (Ctrl+B)"
              aria-label="Toggle navigation sidebar"
              className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer"
            >
              <PanelLeft className="size-4" strokeWidth={1.75} />
            </button>
            <span className="truncate text-sm font-medium text-foreground">
              {mounted ? "Memory" : ""}
            </span>
            {identity.orgId ? (
              <span
                className="hidden truncate font-mono text-xs text-text-tertiary sm:inline"
                title={`Organization ${identity.orgId}`}
              >
                / {identity.orgId.slice(0, 8)}
              </span>
            ) : null}
            {!identity.authRequired ? (
              <span
                className="nb-badge h-5 shrink-0 gap-1 text-[10px]"
                title="CONTEXTA_DASHBOARD_AUTH is off. Anyone who can reach this port can read and write this organization's memories. Set CONTEXTA_DASHBOARD_AUTH=on to re-enable sign-in."
              >
                <ShieldOff className="size-3" strokeWidth={2} />
                Auth off
              </span>
            ) : null}
          </div>

          <div className="flex shrink-0 items-center gap-1.5">
            <IngestObservationModal />
            <EngineStatusBadge />
            <ThemeToggle />
            {identity.name || identity.email ? (
              <span
                title={identity.email ?? undefined}
                className="ml-1 flex size-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-primary-foreground"
                style={{ background: "var(--primary)" }}
              >
                {((identity.name || identity.email || "U") as string)
                  .charAt(0)
                  .toUpperCase()}
              </span>
            ) : null}
          </div>
        </header>

        <main className="flex-1 overflow-y-auto focus:outline-none">
          <div className="mx-auto w-full max-w-5xl px-5 py-8 sm:px-8 sm:py-10">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}

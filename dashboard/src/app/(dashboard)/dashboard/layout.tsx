import { redirect } from "next/navigation";
import { requireSession } from "@/lib/auth-helpers";
import { DashboardSidebar } from "@/components/dashboard-sidebar";
import { ThemeToggle } from "@/components/theme-toggle";
import { EngineStatusBadge } from "@/components/engine-status-badge";
import { IngestObservationModal } from "@/components/ingest-observation-modal";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const session = await requireSession();
  if (!session) redirect("/sign-in");

  return (
    <div className="min-h-screen bg-background text-foreground">
      <DashboardSidebar />
      <div className="md:pl-64 flex flex-col min-h-screen">
        <header className="sticky top-0 z-10 border-b border-border/40 bg-card/60 backdrop-blur-md px-6 sm:px-8 py-4 transition-colors duration-200">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <p className="text-[11px] font-mono tracking-widest text-muted-foreground uppercase">
                {session.user.org_id ? `[ORG: ${session.user.org_id.slice(0, 8)}]` : "[CONTEXTA CORE]"}
              </p>
              <h1 className="text-sm font-normal text-foreground">Memory control plane</h1>
            </div>
            <div className="flex items-center gap-2.5">
              <IngestObservationModal />
              <EngineStatusBadge />
              <ThemeToggle />
              <div className="rounded border border-border/40 bg-secondary/50 px-2.5 py-1 text-xs text-muted-foreground font-mono">
                {session.user.email}
              </div>
              <div className="flex items-center gap-2 text-sm">
                <span className="flex h-7 w-7 items-center justify-center rounded bg-secondary border border-border/40 text-xs font-mono text-foreground">
                  {session.user.name.charAt(0).toUpperCase()}
                </span>
              </div>
            </div>
          </div>
        </header>
        <main className="p-6 sm:p-8 flex-1 flex flex-col">{children}</main>
      </div>
    </div>
  );
}

import { redirect } from "next/navigation";
import { requireSession } from "@/lib/auth-helpers";
import { DashboardSidebar } from "@/components/dashboard-sidebar";
import { ThemeToggle } from "@/components/theme-toggle";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const session = await requireSession();
  if (!session) redirect("/sign-in");

  return (
    <div className="min-h-screen bg-[var(--color-abyss)]">
      <DashboardSidebar />
      <div className="md:pl-64 flex flex-col min-h-screen">
        <header className="sticky top-0 z-10 border-b border-[var(--color-graphite)]/30 bg-[var(--color-abyss)] px-8 py-5 transition-colors duration-200">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <p className="text-xs font-mono tracking-widest text-[var(--color-smoke)] uppercase">
                {session.user.org_id ? `Org: ${session.user.org_id.slice(0, 8)}...` : "contexta"}
              </p>
              <h1 className="text-base font-light text-[var(--color-ghost)]">Memory control plane</h1>
            </div>
            <div className="flex items-center gap-6">
              <ThemeToggle />
              <div className="rounded-xl border border-[var(--color-graphite)]/30 px-3 py-1.5 text-xs text-[var(--color-smoke)] font-mono">
                {session.user.email}
              </div>
              <div className="flex items-center gap-2 text-sm">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-ash)] border border-[var(--color-graphite)]/30 text-xs font-mono text-[var(--color-ghost)]">
                  {session.user.name.charAt(0).toUpperCase()}
                </span>
              </div>
            </div>
          </div>
        </header>
        <main className="p-8 flex-1 flex flex-col">{children}</main>
      </div>
    </div>
  );
}

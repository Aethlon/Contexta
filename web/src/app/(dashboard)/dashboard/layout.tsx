import Link from "next/link";
import { redirect } from "next/navigation";
import {
  BarChart3,
  BookOpen,
  Brain,
  CreditCard,
  KeyRound,
  LogOut,
  Settings,
  Table2,
  Gauge,
} from "lucide-react";
import { signOutAction } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { requireSession } from "@/lib/auth-helpers";

const nav = [
  { href: "/dashboard", label: "Overview", icon: BarChart3 },
  { href: "/dashboard/memories", label: "Memories", icon: Table2 },
  { href: "/dashboard/api-keys", label: "API keys", icon: KeyRound },
  { href: "/dashboard/usage", label: "Usage", icon: Gauge },
  { href: "/dashboard/billing", label: "Billing", icon: CreditCard },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
  { href: "/dashboard/docs", label: "Setup", icon: BookOpen },
];

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const session = await requireSession();
  if (!session) redirect("/sign-in");

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-border bg-background/75 p-4 backdrop-blur md:block">
        <Link className="mb-8 flex items-center gap-2 text-sm font-semibold" href="/dashboard">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Brain className="h-4 w-4" />
          </span>
          contexta
        </Link>
        <nav className="space-y-1">
          {nav.map((item) => (
            <Link
              className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground transition hover:bg-secondary hover:text-foreground"
              href={item.href}
              key={item.href}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          ))}
        </nav>
        <form action={signOutAction} className="absolute bottom-4 left-4 right-4">
          <Button className="w-full justify-start" type="submit" variant="ghost">
            <LogOut className="h-4 w-4" /> Sign out
          </Button>
        </form>
      </aside>
      <div className="md:pl-64">
        <header className="sticky top-0 z-10 border-b border-border bg-background/75 px-6 py-4 backdrop-blur">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">{session.user.org_id ? `Org: ${session.user.org_id.slice(0, 8)}...` : "contexta"}</p>
              <h1 className="text-lg font-semibold">Memory control plane</h1>
            </div>
            <div className="flex items-center gap-3">
              <div className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground">
                {session.user.email}
              </div>
              <div className="flex items-center gap-2 text-sm">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-medium text-primary-foreground">
                  {session.user.name.charAt(0).toUpperCase()}
                </span>
              </div>
            </div>
          </div>
        </header>
        <main className="p-6">{children}</main>
      </div>
    </div>
  );
}

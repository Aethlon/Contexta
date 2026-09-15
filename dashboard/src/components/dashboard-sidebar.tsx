"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, BookOpen, KeyRound, LogOut, Settings, Table2, Bot } from "lucide-react";
import { signOutAction } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { ContextaMark } from "@/components/contexta-logo";

const nav = [
  { href: "/dashboard", label: "Overview", icon: BarChart3 },
  { href: "/dashboard/memories", label: "Memories", icon: Table2 },
  { href: "/dashboard/api-keys", label: "API keys", icon: KeyRound },
  { href: "/dashboard/mcp", label: "MCP Protocol", icon: Bot },
  { href: "/dashboard/setup", label: "Setup", icon: BookOpen },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

export function DashboardSidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-border/40 bg-card/90 backdrop-blur-md p-6 md:block">
      <Link className="mb-8 flex items-center gap-2.5 text-sm font-mono text-foreground select-none" href="/dashboard">
        <span className="flex size-7 items-center justify-center rounded border border-border/40 bg-secondary/60 text-foreground">
          <ContextaMark className="size-4" />
        </span>
        <span className="text-base tracking-tight font-normal">contexta</span>
        <span className="rounded bg-foreground/10 px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
          v0.2
        </span>
      </Link>
      <nav className="space-y-1">
        {nav.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              className={`flex items-center gap-2.5 rounded px-3 py-2 text-xs font-mono transition-all relative ${
                isActive
                  ? "text-foreground font-normal bg-secondary border border-border/40 shadow-xs"
                  : "text-muted-foreground hover:text-foreground hover:bg-secondary/40"
              }`}
              href={item.href}
              key={item.href}
            >
              <item.icon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <form action={signOutAction} className="absolute bottom-6 left-6 right-6">
        <Button className="w-full justify-start rounded border border-border/40 bg-secondary/30 font-mono text-xs text-muted-foreground hover:text-red-400 hover:border-red-500/30" type="submit" variant="ghost">
          <LogOut className="h-3.5 w-3.5" strokeWidth={1.5} />
          <span>Sign out</span>
        </Button>
      </form>
    </aside>
  );
}

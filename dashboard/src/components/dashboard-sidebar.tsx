"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  Bot,
  Database,
  KeyRound,
  LayoutGrid,
  Rocket,
  Settings,
} from "lucide-react";
import { ContextaMark } from "@/components/contexta-logo";
import { TenantSwitcher } from "@/components/tenant-switcher";
import type { OperatorIdentity } from "@/lib/dashboard-identity";

const nav = [
  { href: "/dashboard", label: "Overview", icon: LayoutGrid },
  { href: "/dashboard/welcome", label: "Get started", icon: Rocket },
  { href: "/dashboard/memories", label: "Memories", icon: Database },
  { href: "/dashboard/api-keys", label: "API keys", icon: KeyRound },
  { href: "/dashboard/mcp", label: "MCP", icon: Bot },
];

const secondary = [
  { href: "/dashboard/setup", label: "Setup", icon: BookOpen },
  { href: "/dashboard/docs", label: "Docs", icon: BookOpen },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

interface DashboardSidebarProps {
  identity: OperatorIdentity;
}

export function DashboardSidebar({ identity }: DashboardSidebarProps) {
  const pathname = usePathname();

  const renderItem = (item: (typeof nav)[number]) => {
    const isActive = pathname === item.href;
    return (
      <Link
        key={item.href}
        href={item.href}
        className={`nb-nav-item ${isActive ? "nb-nav-item-active" : ""}`}
        aria-current={isActive ? "page" : undefined}
      >
        <item.icon className="size-4 shrink-0" strokeWidth={1.75} />
        <span className="truncate">{item.label}</span>
      </Link>
    );
  };

  return (
    <aside className="flex h-full w-60 flex-col">
      {/* Brand */}
      <div className="flex h-12 shrink-0 items-center gap-2 px-3">
        <Link href="/dashboard" className="flex min-w-0 items-center gap-2">
          <span className="flex size-5 shrink-0 items-center justify-center text-foreground">
            <ContextaMark className="size-4" />
          </span>
          <span className="truncate text-sm font-semibold tracking-tight text-foreground">
            contexta
          </span>
        </Link>
      </div>

      {/* Primary navigation */}
      <nav className="flex-1 overflow-y-auto px-2 pb-2">
        <div className="space-y-0.5">{nav.map(renderItem)}</div>

        <hr className="nb-divider my-3" />

        <div className="space-y-0.5">{secondary.map(renderItem)}</div>
      </nav>

      <TenantSwitcher identity={identity} />
    </aside>
  );
}

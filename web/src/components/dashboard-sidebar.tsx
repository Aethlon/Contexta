"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, BookOpen, Brain, KeyRound, LogOut, Settings, Table2 } from "lucide-react";
import { signOutAction } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";

const nav = [
  { href: "/dashboard", label: "Overview", icon: BarChart3 },
  { href: "/dashboard/memories", label: "Memories", icon: Table2 },
  { href: "/dashboard/api-keys", label: "API keys", icon: KeyRound },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
  { href: "/dashboard/docs", label: "Setup", icon: BookOpen },
];

export function DashboardSidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6 md:block">
      <Link className="mb-10 flex items-center gap-2.5 text-sm font-light text-[var(--color-ghost)] select-none" href="/dashboard">
        <Brain className="h-5 w-5 text-[var(--color-smoke)]" strokeWidth={1.2} />
        <span className="text-base tracking-tight font-normal">contexta</span>
      </Link>
      <nav className="space-y-1.5">
        {nav.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              className={`flex items-center gap-3 rounded-xl px-4 py-2.5 text-sm font-light transition-all relative ${
                isActive
                  ? "text-[var(--color-ghost)] font-normal"
                  : "text-[var(--color-smoke)] hover:text-[var(--color-ghost)]"
              }`}
              href={item.href}
              key={item.href}
            >
              {isActive && (
                <motion.div
                  layoutId="activeNavIndicator"
                  className="absolute inset-0 bg-[var(--color-charcoal)] rounded-xl z-0"
                  transition={{ type: "spring", stiffness: 380, damping: 30 }}
                />
              )}
              <span className="relative z-10 flex items-center gap-3">
                <item.icon className="h-4 w-4" strokeWidth={1.2} />
                {item.label}
              </span>
            </Link>
          );
        })}
      </nav>
      <form action={signOutAction} className="absolute bottom-6 left-6 right-6">
        <Button className="w-full justify-start hover:text-red-400" type="submit" variant="ghost">
          <LogOut className="h-4 w-4" strokeWidth={1.2} /> Sign out
        </Button>
      </form>
    </aside>
  );
}

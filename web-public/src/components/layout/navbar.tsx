"use client";

import { useEffect, useState } from "react";
import { HugeiconsIcon } from "@hugeicons/react";
import { ArrowUpRight01Icon, Menu01Icon } from "@hugeicons/core-free-icons";
import { Button, buttonVariants, Sheet, SheetContent, SheetFooter, SheetHeader, SheetTitle, SheetTrigger } from "@aethlon/components";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { label: "Features", href: "#features" },
  { label: "How it works", href: "#how-it-works" },
  { label: "Pricing", href: "#pricing" },
  { label: "FAQ", href: "#faq" },
];

export function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-40 bg-background/95 transition-[border-color] duration-200 ease-[var(--ease-snappy)]",
        scrolled ? "border-b border-border/30" : "border-b border-transparent",
      )}
    >
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 sm:px-6">
        <a
          href="#top"
          className="font-semibold tracking-tight text-foreground rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          Contexta
        </a>

        <nav className="ml-6 hidden items-center gap-1 lg:flex" aria-label="Primary">
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="rounded-lg px-3 py-1.5 font-light text-sm text-muted-foreground transition-colors duration-200 ease-[var(--ease-snappy)] hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 outline-none"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="ml-auto hidden items-center gap-2 lg:flex">
          <a
            href="https://app.contexta.dev"
            target="_blank"
            rel="noopener noreferrer"
            className={buttonVariants({
              variant: "ghost",
              size: "sm",
              className:
                "text-muted-foreground hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50",
            })}
          >
            Dashboard
            <HugeiconsIcon icon={ArrowUpRight01Icon} size={14} strokeWidth={1.2} />
          </a>
          <a
            href="https://app.contexta.dev"
            target="_blank"
            rel="noopener noreferrer"
            className={buttonVariants({
              variant: "default",
              size: "sm",
              className: "focus-visible:ring-3 focus-visible:ring-ring/50",
            })}
          >
            Start free
          </a>
        </div>

        <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
          <SheetTrigger
            render={
              <Button
                variant="ghost"
                size="icon"
                className="lg:hidden"
                aria-label="Open menu"
              />
            }
          >
            <HugeiconsIcon icon={Menu01Icon} size={16} strokeWidth={1.2} />
          </SheetTrigger>
          <SheetContent side="right">
            <SheetHeader>
              <SheetTitle className="font-semibold">Contexta</SheetTitle>
            </SheetHeader>
            <nav className="flex flex-col gap-1 px-4" aria-label="Mobile">
              {NAV_LINKS.map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  onClick={() => setMenuOpen(false)}
                  className="rounded-lg px-3 py-2 font-light text-sm text-muted-foreground transition-colors duration-200 ease-[var(--ease-snappy)] hover:text-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  {link.label}
                </a>
              ))}
            </nav>
            <SheetFooter>
              <a
                href="https://app.contexta.dev"
                target="_blank"
                rel="noopener noreferrer"
                className={buttonVariants({
                  variant: "ghost",
                  className: "w-full",
                })}
              >
                Dashboard
                <HugeiconsIcon icon={ArrowUpRight01Icon} size={16} strokeWidth={1.2} />
              </a>
              <a
                href="https://app.contexta.dev"
                target="_blank"
                rel="noopener noreferrer"
                className={buttonVariants({
                  variant: "default",
                  className: "w-full",
                })}
              >
                Start free
              </a>
            </SheetFooter>
          </SheetContent>
        </Sheet>
      </div>
    </header>
  );
}

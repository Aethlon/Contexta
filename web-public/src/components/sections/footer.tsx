import { HugeiconsIcon } from "@hugeicons/react";
import { ArrowUpRight01Icon, DiscordIcon, GithubIcon } from "@hugeicons/core-free-icons";
import { buttonVariants } from "@aethlon/components";

const columns = [
  {
    heading: "Product",
    links: [
      { label: "Features", href: "#features" },
      { label: "Pricing", href: "#pricing" },
      { label: "Dashboard", href: "https://app.contexta.dev" },
      { label: "Docs", href: "https://docs.contexta.dev" },
    ],
  },
  {
    heading: "Community",
    links: [
      { label: "GitHub", href: "https://github.com/Aethlon/Contexta" },
      { label: "Discord", href: "https://discord.gg/contexta" },
      { label: "Changelog", href: "https://github.com/Aethlon/Contexta/releases" },
    ],
  },
  {
    heading: "Legal",
    links: [
      { label: "License", href: "https://opensource.org/licenses/Apache-2.0" },
      { label: "Contact", href: "mailto:licensing@contexta.dev" },
    ],
  },
];

export function Footer() {
  return (
    <footer className="border-t border-border/30">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="grid gap-10 md:grid-cols-[minmax(0,1.5fr)_repeat(3,minmax(0,1fr))]">
          <div>
            <a
              href="#top"
              className="font-semibold tracking-tight text-foreground rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              Contexta
            </a>
            <p className="mt-3 max-w-xs text-sm font-light text-muted-foreground">
              The memory intelligence layer for AI agents. Observe to remember,
              context to recall.
            </p>
            <div className="mt-5 flex items-center gap-2">
              <a
                href="https://github.com/Aethlon/Contexta"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Contexta on GitHub"
                className={buttonVariants({
                  variant: "ghost",
                  size: "icon-sm",
                })}
              >
                <HugeiconsIcon icon={GithubIcon} size={16} strokeWidth={1.2} />
              </a>
              <a
                href="https://discord.gg/contexta"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Contexta on Discord"
                className={buttonVariants({
                  variant: "ghost",
                  size: "icon-sm",
                })}
              >
                <HugeiconsIcon icon={DiscordIcon} size={16} strokeWidth={1.2} />
              </a>
              <a
                href="https://app.contexta.dev"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Contexta dashboard"
                className={buttonVariants({
                  variant: "ghost",
                  size: "icon-sm",
                })}
              >
                <HugeiconsIcon
                  icon={ArrowUpRight01Icon}
                  size={16}
                  strokeWidth={1.2}
                />
              </a>
            </div>
          </div>

          {columns.map((column) => (
            <nav key={column.heading} aria-label={column.heading}>
              <p className="text-micro">{column.heading}</p>
              <ul className="mt-4 grid gap-2.5">
                {column.links.map((link) => (
                  <li key={link.label}>
                    <a
                      href={link.href}
                      className="rounded-lg font-light text-sm text-muted-foreground transition-colors duration-200 ease-[var(--ease-snappy)] hover:text-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="mt-14 flex flex-wrap items-center justify-between gap-3 border-t border-border/30 pt-8">
          <p className="font-dotmatrix text-xs text-muted-foreground">
            © 2026 CONTEXTA
          </p>
          <p className="font-dotmatrix text-xs text-muted-foreground">
            BUILT ON @AETHLON/COMPONENTS
          </p>
        </div>
      </div>
    </footer>
  );
}

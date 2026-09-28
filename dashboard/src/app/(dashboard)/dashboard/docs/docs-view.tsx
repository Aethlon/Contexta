"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ChevronRight, Search } from "lucide-react";
import { CopyButton } from "./copy-button";
import { DocsContent, type DocContext, type DocSection } from "./docs-content";

/**
 * Documentation browser.
 *
 * Previously one long scrolling page with a tab strip. That works on a phone and
 * badly on a laptop: everything is on screen at once and there is no way to jump
 * to the part you need. This is a topic list plus a content window, so the
 * sidebar and the article are independent and only one is scrolled.
 */

export function DocsView({
  ctx,
  sections,
}: {
  ctx: DocContext;
  sections: DocSection[];
}) {
  const [active, setActive] = useState(sections[0]?.id ?? "");
  const [query, setQuery] = useState("");

  // Deep link: /dashboard/docs#mcp
  useEffect(() => {
    const hash = window.location.hash.replace("#", "");
    if (hash && sections.some((s) => s.id === hash)) setActive(hash);
  }, [sections]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sections;
    return sections.filter(
      (s) =>
        s.title.toLowerCase().includes(q) || s.blurb.toLowerCase().includes(q),
    );
  }, [query, sections]);

  const current = sections.find((s) => s.id === active) ?? sections[0];

  return (
    <div className="grid gap-8 lg:grid-cols-[13rem_1fr] lg:gap-10">
      {/* Topic list */}
      <aside className="lg:sticky lg:top-4 lg:self-start">
        <div className="relative mb-3">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter topics"
            aria-label="Filter documentation topics"
            className="nb-input h-8 pl-8 text-[13px]"
          />
        </div>

        <nav className="space-y-0.5" aria-label="Documentation topics">
          {filtered.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => {
                setActive(s.id);
                window.history.replaceState(null, "", `#${s.id}`);
              }}
              className={`nb-nav-item w-full text-left ${
                s.id === current?.id ? "nb-nav-item-active" : ""
              }`}
              aria-current={s.id === current?.id ? "true" : undefined}
            >
              <ChevronRight className="size-3.5 shrink-0 opacity-40" strokeWidth={2} />
              <span className="truncate">{s.title}</span>
            </button>
          ))}
          {filtered.length === 0 && (
            <p className="px-2 py-3 text-[13px] text-muted-foreground">No topics match.</p>
          )}
        </nav>

        <div className="mt-5 border-t border-border pt-4">
          <p className="px-2 text-[13px] leading-relaxed text-muted-foreground">
            Looking to wire up an agent?{" "}
            <Link
              href="/dashboard/mcp"
              className="text-foreground underline underline-offset-2"
            >
              The MCP page does it in two steps
            </Link>
            .
          </p>
        </div>
      </aside>

      {/* Content window */}
      <div className="min-w-0">
        {current ? (
          <DocsContent section={current} ctx={ctx} />
        ) : (
          <p className="text-[13px] text-muted-foreground">Nothing to show.</p>
        )}
      </div>
    </div>
  );
}

export { CopyButton };

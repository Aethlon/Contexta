import type { Metadata } from "next";
import { Sidebar } from "@/components/Sidebar";
import { Search } from "@/components/Search";
import "@/styles/docs.css";

export const metadata: Metadata = {
  title: "contexta Docs — Memory Intelligence for AI Agents",
  description:
    "Self-hosted, offline-first long-term memory for AI agents. Hybrid retrieval, durable ingestion, and truth maintenance on infrastructure you own.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <div className="docs-layout">
          <header className="docs-header">
            <div className="docs-header-inner">
              <a href="/" className="docs-logo">
                <span className="docs-logo-mark">M</span>
                <span className="docs-logo-text">contexta</span>
              </a>
              <nav className="docs-header-nav">
                <a href="/quickstart">Quickstart</a>
                <a href="/concepts">Concepts</a>
                <a href="/reference/api">API</a>
                <a href="/reference/sdks">SDKs</a>
                <a href="/licensing">Licensing</a>
                <a href="/changelog">Changelog</a>
              </nav>
              <div className="docs-header-right">
                <Search />
                <a href="/quickstart" className="docs-btn docs-btn-primary">Get started</a>
              </div>
            </div>
          </header>
          <div className="docs-body">
            <Sidebar />
            <main className="docs-content">
              <article className="docs-article">
                {children}
              </article>
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}

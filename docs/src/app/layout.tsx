import type { Metadata } from "next";
import { Sidebar } from "@/components/Sidebar";
import { Search } from "@/components/Search";
import "@/styles/docs.css";

export const metadata: Metadata = {
  title: "contexta Docs — Memory Intelligence for AI Agents",
  description: "Build agents that remember. SDK-first memory layer with hybrid retrieval, extraction, and lifecycle management.",
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
                <a href="/reference/sdks">SDKs</a>
                <a href="/pricing">Pricing</a>
                <a href="/changelog">Changelog</a>
              </nav>
              <div className="docs-header-right">
                <Search />
                <a href="https://app.contexta.dev" className="docs-btn docs-btn-primary" target="_blank" rel="noreferrer">Dashboard</a>
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

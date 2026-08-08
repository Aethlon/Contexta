"use client";

import { useState, useCallback } from "react";

export function Search() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setOpen(false);
      setQuery("");
    }
  }, []);

  return (
    <div className="search-wrapper">
      <button
        className="search-trigger"
        onClick={() => setOpen(true)}
        aria-label="Search documentation"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.35-4.35" />
        </svg>
        <span className="search-trigger-text">Search docs...</span>
        <kbd className="search-kbd">Ctrl+K</kbd>
      </button>

      {open && (
        <div className="search-overlay" onClick={() => { setOpen(false); setQuery(""); }}>
          <div className="search-dialog" onClick={(e) => e.stopPropagation()} onKeyDown={handleKeyDown}>
            <div className="search-input-wrapper">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.35-4.35" />
              </svg>
              <input
                className="search-input"
                type="text"
                placeholder="Search documentation..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                autoFocus
              />
              <button className="search-close" onClick={() => { setOpen(false); setQuery(""); }} aria-label="Close search">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 6 6 18" /><path d="m6 6 12 12" />
                </svg>
              </button>
            </div>
            <div className="search-results">
              {query.length > 0 ? (
                <p className="search-empty">Press Enter to search the full docs site.</p>
              ) : (
                <div className="search-hints">
                  <p>Try searching for: <code>observe</code>, <code>retrieval</code>, <code>API key</code></p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

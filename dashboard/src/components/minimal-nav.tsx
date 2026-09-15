"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";

const GITHUB_REPO = "https://github.com/Aethlon/Contexta";

interface CommandItem {
  id: string;
  label: string;
  description: string;
  shortcut?: string;
  action: () => void;
  section: string;
}

const COMMAND_ITEMS: CommandItem[] = [
  { id: "github", label: "GitHub Repository", description: "View source code & contribute", shortcut: "⌘G", section: "Resources", action: () => window.open(GITHUB_REPO, "_blank") },
  { id: "docs", label: "Documentation", description: "API reference & guides", shortcut: "⌘D", section: "Resources", action: () => window.open("/docs", "_blank") },
  { id: "discord", label: "Discord Community", description: "Join 2,400+ developers", shortcut: "⌘K", section: "Resources", action: () => window.open("https://discord.gg/contexta", "_blank") },
  { id: "pricing", label: "Pricing", description: "Self-hosted & cloud plans", section: "Resources", action: () => window.open("/pricing", "_blank") },
  { id: "changelog", label: "Changelog", description: "Recent updates & fixes", section: "Resources", action: () => window.open("/changelog", "_blank") },
  { id: "architecture", label: "Architecture Deep Dive", description: "Technical architecture overview", section: "Navigate", action: () => document.getElementById("architecture")?.scrollIntoView({ behavior: "smooth" }) },
  { id: "benchmarks", label: "50K Benchmarks", description: "Performance data & comparisons", section: "Navigate", action: () => document.getElementById("benchmarks")?.scrollIntoView({ behavior: "smooth" }) },
  { id: "playground", label: "Live Playground", description: "Test extraction engine", section: "Navigate", action: () => document.getElementById("playground")?.scrollIntoView({ behavior: "smooth" }) },
  { id: "console", label: "Open Console", description: "Sign in to your enclave", shortcut: "⌘E", section: "Navigate", action: () => window.location.href = "/sign-in" },
];

export function MinimalNav() {
  const [isScrolled, setIsScrolled] = useState(false);
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 100);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setShowCommandPalette(true);
        setCommandQuery("");
        setSelectedIndex(0);
      }
      if (e.key === "Escape") {
        setShowCommandPalette(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    if (showCommandPalette) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [showCommandPalette]);

  const filteredItems = COMMAND_ITEMS.filter(item =>
    item.label.toLowerCase().includes(commandQuery.toLowerCase()) ||
    item.description.toLowerCase().includes(commandQuery.toLowerCase()) ||
    item.shortcut?.toLowerCase().includes(commandQuery.toLowerCase())
  );

  const handleSelect = (item: CommandItem) => {
    item.action();
    setShowCommandPalette(false);
    setCommandQuery("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex(prev => Math.min(prev + 1, filteredItems.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex(prev => Math.max(prev - 1, 0));
    } else if (e.key === "Enter" && filteredItems[selectedIndex]) {
      handleSelect(filteredItems[selectedIndex]);
    }
  };

  const groupedItems = filteredItems.reduce((acc, item) => {
    if (!acc[item.section]) acc[item.section] = [];
    acc[item.section].push(item);
    return acc;
  }, {} as Record<string, CommandItem[]>);

  return (
    <>
      <header className={`fixed top-5 left-1/2 -translate-x-1/2 z-50 w-full max-w-[1400px] px-4 sm:px-6 transition-all duration-500 ${isScrolled ? "opacity-100" : "opacity-100"} pointer-events-auto`}>
        <nav ref={navRef} className="flex items-center justify-between w-full max-w-5xl mx-auto px-4 sm:px-6 py-2.5 rounded-full glass-2 shadow-elev-2">
          {/* Brand */}
          <Link href="/" className="flex items-center gap-2.5 group pointer-events-auto" aria-label="Contexta Home">
            <motion.div
              className="flex items-center justify-center w-7 h-7 rounded-lg bg-white/[0.04] group-hover:bg-white/[0.08] transition-colors"
              whileHover={{ scale: 1.1, rotate: 12 }}
              transition={{ type: "spring", stiffness: 300, damping: 20 }}
            >
              <ContextaGlyph className="h-4 w-4 text-blue-400" />
            </motion.div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold tracking-tight text-white">Contexta</span>
              <span className="hidden md:inline-flex px-2 py-0.5 rounded-full bg-white/[0.04] text-[10px] font-mono text-[#6B7280]">
                v0.2.0-beta
              </span>
            </div>
          </Link>

          {/* Navigation Links */}
          <div className="hidden md:flex items-center gap-1">
            {[
              { href: "#architecture", label: "Architecture" },
              { href: "#benchmarks", label: "Benchmarks" },
              { href: "#playground", label: "Playground" },
            ].map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="relative px-3 py-1.5 text-xs font-mono uppercase tracking-wider text-[#6B7280] hover:text-white transition-colors after:absolute after:bottom-1 after:left-1/2 after:-translate-x-1/2 after:w-0 after:h-0.5 after:bg-blue-400 after:transition-all hover:after:w-3/4"
              >
                {item.label}
              </a>
            ))}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            {/* Command Palette Trigger */}
            <button
              onClick={() => { setShowCommandPalette(true); setCommandQuery(""); setSelectedIndex(0); }}
              className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/[0.03] hover:bg-white/[0.06] text-xs font-mono text-[#6B7280] hover:text-white transition-all"
              aria-label="Open command palette (⌘K)"
            >
              <kbd className="px-1.5 py-0.5 rounded bg-white/[0.06] text-[10px] font-mono text-[#6B7280]">⌘K</kbd>
            </button>

            <Link
              href="/sign-in"
              className="hidden sm:block px-3 py-1.5 text-xs font-mono text-[#6B7280] hover:text-white transition-colors"
            >
              Sign In
            </Link>

            <Link
              href="/sign-up"
              className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-blue-600 hover:bg-blue-500 text-xs font-medium text-white shadow-lg shadow-blue-600/25 transition-all hover:scale-[1.02] active:scale-[0.98]"
            >
              <span>Console</span>
              <motion.span
                whileHover={{ x: 4 }}
                transition={{ type: "spring", stiffness: 400, damping: 20 }}
              >
                →
              </motion.span>
            </Link>
          </div>
        </nav>
      </header>

      {/* Command Palette */}
      <AnimatePresence>
        {showCommandPalette && (
          <motion.div
            className="cmdk-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowCommandPalette(false)}
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
          >
            <motion.div className="cmdk-window" initial={{ opacity: 0, scale: 0.96, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.96, y: -20 }} transition={{ type: "spring", stiffness: 300, damping: 25 }} onClick={(e) => e.stopPropagation()}>
              <div className="relative">
                <div className="absolute left-4 top-1/2 -translate-y-1/2 text-micro text-[#3D4450] pointer-events-none">
                  <kbd className="px-1.5 py-0.5 rounded bg-white/[0.06]">⌘</kbd>
                  <kbd className="px-1.5 py-0.5 rounded bg-white/[0.06]">K</kbd>
                </div>
                <input
                  ref={inputRef}
                  type="text"
                  value={commandQuery}
                  onChange={(e) => { setCommandQuery(e.target.value); setSelectedIndex(0); }}
                  onKeyDown={handleKeyDown}
                  className="cmdk-input text-base font-light placeholder:text-[#3D4450]"
                  placeholder="Search commands, navigate, or take action..."
                  aria-label="Command palette search"
                  autoComplete="off"
                  spellCheck={false}
                />
              </div>

              <div className="cmdk-list" role="listbox" aria-label="Commands">
                {Object.entries(groupedItems).map(([section, items]) => (
                  <div key={section} className="space-y-1">
                    <div className="px-3 py-2 text-[10px] font-mono uppercase tracking-widest text-[#3D4450]">
                      {section}
                    </div>
                    {items.map((item) => {
                      const isSelected = filteredItems.indexOf(item) === selectedIndex;
                      return (
                        <motion.div
                          key={item.id}
                          role="option"
                          aria-selected={isSelected}
                          className={`cmdk-item ${isSelected ? "bg-white/[0.08] text-white" : ""}`}
                          onClick={() => handleSelect(item)}
                          onMouseEnter={() => setSelectedIndex(filteredItems.indexOf(item))}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          exit={{ opacity: 0, x: 10 }}
                          transition={{ duration: 0.15 }}
                        >
                          <span className="flex-1">{item.label}</span>
                          <span className="text-[11px] text-[#3D4450]">{item.description}</span>
                          {item.shortcut && (
                            <kbd className="cmdk-item-kbd">{item.shortcut}</kbd>
                          )}
                        </motion.div>
                      );
                    })}
                  </div>
                ))}
                {filteredItems.length === 0 && (
                  <div className="px-4 py-8 text-center text-[#3D4450] text-sm">
                    No commands match &ldquo;{commandQuery}&rdquo;
                  </div>
                )}
              </div>

              <div className="px-4 py-3 border-t border-white/[0.04] text-micro text-[#3D4450] flex items-center justify-between">
                <span>Contexta v0.2.0-beta</span>
                <span>⌘K to close</span>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function ContextaGlyph({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="glyphGradient" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#3B82F6"/>
          <stop offset="50%" stopColor="#8B5CF6"/>
          <stop offset="100%" stopColor="#06B6D4"/>
        </linearGradient>
      </defs>
      {/* Isometric cube representing memory node */}
      <path
        d="M16 2 L30 8 V24 L16 30 L2 24 V8 L16 2 Z"
        stroke="url(#glyphGradient)"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* Top face highlight */}
      <path
        d="M16 2 L30 8 L16 14 L2 8 Z"
        fill="url(#glyphGradient)"
        fillOpacity="0.15"
      />
      {/* Connection lines representing graph edges */}
      <path d="M16 14 V22" stroke="url(#glyphGradient)" strokeWidth="1" strokeLinecap="round" opacity="0.6"/>
      <path d="M16 14 L8 19" stroke="url(#glyphGradient)" strokeWidth="1" strokeLinecap="round" opacity="0.6"/>
      <path d="M16 14 L24 19" stroke="url(#glyphGradient)" strokeWidth="1" strokeLinecap="round" opacity="0.6"/>
      {/* Pulse ring */}
      <circle cx="16" cy="16" r="14" stroke="url(#glyphGradient)" strokeWidth="0.5" fill="none" opacity="0.3"/>
    </svg>
  );
}
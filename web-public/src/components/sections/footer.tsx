"use client";

import React, { useState } from "react";
import { Github, Mail, Shield, Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";

export function Footer() {
  const [copied, setCopied] = useState(false);
  const command = "git clone https://github.com/Aethlon/Contexta.git && cd Contexta && docker compose up --build";

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy command: ", err);
    }
  };

  return (
    <footer className="border-t border-[var(--color-border)] bg-[var(--color-abyss)]" id="quickstart">
      {/* Final CTA Banner */}
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-20">
        <div className="relative overflow-hidden rounded-3xl border border-[var(--color-purple)]/20 bg-gradient-to-br from-[var(--color-ash)] via-[var(--color-charcoal)] to-[var(--color-abyss)] px-8 py-16 text-center shadow-2xl">
          {/* Subtle Glows */}
          <div className="absolute -top-24 -left-24 h-48 w-48 rounded-full bg-[var(--color-purple)]/10 blur-[80px]" />
          <div className="absolute -bottom-24 -right-24 h-48 w-48 rounded-full bg-[var(--color-purple)]/10 blur-[80px]" />

          <div className="relative z-10 max-w-2xl mx-auto">
            <h2 className="text-3xl font-bold tracking-tight text-[var(--color-foreground)] sm:text-4xl mb-4">
              Prefer to self-host?
            </h2>
            <p className="text-base text-[var(--color-smoke)] mb-8 font-light leading-relaxed">
              The Community Edition is free under Apache 2.0. Boot the complete Contexta stack — Go Gateway, FastAPI, Redis, Postgres + pgvector, Celery Workers, and the management explorer — with a single command.
            </p>

            {/* Quickstart Command Box */}
            <div className="flex flex-col sm:flex-row items-stretch justify-center gap-2 max-w-lg mx-auto bg-[var(--color-abyss)]/60 rounded-xl p-2 border border-[var(--color-border)] mb-4">
              <div className="flex-1 font-mono text-xs text-zinc-300 flex items-center justify-start px-3 py-3 overflow-x-auto whitespace-nowrap">
                <span className="text-[var(--color-purple)] mr-2 select-none">$</span>
                <span className="select-all">{command}</span>
              </div>
              <Button
                variant="gold"
                size="md"
                onClick={handleCopy}
                className="gap-2 flex-shrink-0"
              >
                {copied ? (
                  <>
                    <Check className="h-4 w-4" />
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-4 w-4" />
                    <span>Copy</span>
                  </>
                )}
              </Button>
            </div>
            
            <p className="text-xs text-[var(--color-smoke)] font-mono">
              Requires Docker & Docker Compose v2.0+
            </p>
          </div>
        </div>

        {/* Footer Links & Credits */}
        <div className="mt-20 pt-8 border-t border-[var(--color-border)] flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-2">
            <span className="font-mono text-base font-bold text-[var(--color-foreground)] tracking-tight">
              Contexta
            </span>
          </div>

          <div className="flex flex-wrap justify-center gap-x-8 gap-y-2 text-sm text-[var(--color-smoke)]">
            <a href="https://app.contexta.dev" target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 hover:text-[var(--color-foreground)] transition-colors">
              <span>Dashboard</span>
            </a>
            <a href="https://contexta.dev/docs" target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 hover:text-[var(--color-foreground)] transition-colors">
              <span>Docs</span>
            </a>
            <a href="#pricing" className="flex items-center gap-1.5 hover:text-[var(--color-foreground)] transition-colors">
              <span>Pricing</span>
            </a>
            <a href="https://github.com/Aethlon/Contexta" target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 hover:text-[var(--color-foreground)] transition-colors">
              <Github className="h-4 w-4" />
              <span>GitHub</span>
            </a>
            <a href="mailto:licensing@contexta.dev" className="flex items-center gap-1.5 hover:text-[var(--color-foreground)] transition-colors">
              <Mail className="h-4 w-4" />
              <span>licensing@contexta.dev</span>
            </a>
            <a href="https://github.com/Aethlon/Contexta/blob/main/LICENSE" target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 hover:text-[var(--color-foreground)] transition-colors">
              <Shield className="h-4 w-4" />
              <span>License (Apache 2.0)</span>
            </a>
          </div>

          <div className="text-xs text-[var(--color-smoke)] text-center md:text-right font-light">
            &copy; 2026 Contexta. All rights reserved.
          </div>
        </div>
      </div>
    </footer>
  );
}

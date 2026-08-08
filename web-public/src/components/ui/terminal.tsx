"use client";

import React, { useState } from "react";
import { Check, Copy, Terminal as TerminalIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface TerminalProps {
  tabs: {
    [key: string]: {
      label: string;
      code: string;
      language: string;
    };
  };
}

export function Terminal({ tabs }: TerminalProps) {
  const tabKeys = Object.keys(tabs);
  const [activeTab, setActiveTab] = useState(tabKeys[0]);
  const [copied, setCopied] = useState(false);

  const activeContent = tabs[activeTab];

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(activeContent.code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy text: ", err);
    }
  };

  return (
    <div className="w-full overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-charcoal)] shadow-2xl">
      {/* Terminal Title Bar */}
      <div className="flex h-12 items-center justify-between border-b border-[var(--color-border)] px-4 bg-[var(--color-ash)]">
        <div className="flex items-center gap-1.5">
          {/* Dot decorations */}
          <span className="h-3 w-3 rounded-full bg-red-500/20 border border-red-500/30" />
          <span className="h-3 w-3 rounded-full bg-yellow-500/20 border border-yellow-500/30" />
          <span className="h-3 w-3 rounded-full bg-green-500/20 border border-green-500/30" />
          
          <div className="ml-4 flex items-center gap-2 text-xs font-mono text-[var(--color-smoke)]">
            <TerminalIcon className="h-3.5 w-3.5" />
            <span>sdk_integration.{activeContent.language}</span>
          </div>
        </div>

        {/* Copy Button */}
        <button
          onClick={handleCopy}
          className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs text-[var(--color-smoke)] transition-colors hover:bg-[var(--color-charcoal)] hover:text-[var(--color-foreground)] active:scale-95"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5 text-green-500" />
              <span className="text-green-500 font-medium">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[var(--color-border)] bg-[var(--color-ash)]/40 px-2 overflow-x-auto">
        {tabKeys.map((key) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={cn(
              "px-4 py-2.5 text-xs font-mono border-b-2 transition-all",
              activeTab === key
                ? "border-[var(--color-purple)] text-[var(--color-purple)] font-medium"
                : "border-transparent text-[var(--color-smoke)] hover:text-[var(--color-foreground)]"
            )}
          >
            {tabs[key].label}
          </button>
        ))}
      </div>

      {/* Code Area */}
      <div className="overflow-x-auto p-5 font-mono text-sm leading-relaxed text-zinc-300 bg-[var(--color-abyss)]/60 max-h-[450px]">
        <pre className="grid grid-cols-[auto_1fr] gap-x-4">
          <code>
            {activeContent.code.split("\n").map((_, idx) => (
              <span
                key={idx}
                className="block text-right select-none text-[var(--color-smoke)]/40 text-xs pr-1"
              >
                {idx + 1}
              </span>
            ))}
          </code>
          <code className="text-left select-text whitespace-pre overflow-x-auto">
            {activeContent.code.split("\n").map((line, idx) => {
              // Simple client side regex highlighting for key keywords
              
              // highlight comments
              if (line.trim().startsWith("#") || line.trim().startsWith("//")) {
                return (
                  <span key={idx} className="block text-zinc-500 italic">
                    {line}
                  </span>
                );
              }

              // simple highlight logic
              return (
                <span key={idx} className="block min-h-[1.5rem]">
                  {line.split(/(\s+|\(|\)|\{|\}|\[|\]|=|,|:)/).map((token, tIdx) => {
                    const cleanToken = token.trim();
                    const isKeyword = ["import", "from", "await", "const", "let", "def", "return"].includes(cleanToken);
                    const isBrand = ["contexta", "contexta_client"].includes(cleanToken);
                    const isString = (token.startsWith('"') && token.endsWith('"')) || (token.startsWith("'") && token.endsWith("'")) || (token.startsWith("`") && token.endsWith("`"));

                    if (isKeyword) {
                      return <span key={tIdx} className="text-pink-500/80">{token}</span>;
                    }
                    if (isBrand) {
                      return <span key={tIdx} className="text-[var(--color-purple)] font-medium">{token}</span>;
                    }
                    if (isString) {
                      return <span key={tIdx} className="text-emerald-400/80">{token}</span>;
                    }
                    if (cleanToken.startsWith("user_") || cleanToken.startsWith("usr_") || cleanToken.startsWith("ctx_")) {
                      return <span key={tIdx} className="text-yellow-400/80">{token}</span>;
                    }
                    return token;
                  })}
                </span>
              );
            })}
          </code>
        </pre>
      </div>
    </div>
  );
}

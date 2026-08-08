"use client";

import React, { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface AccordionItemProps {
  question: string;
  answer: string;
  isOpen: boolean;
  onToggle: () => void;
}

export function AccordionItem({
  question,
  answer,
  isOpen,
  onToggle
}: AccordionItemProps) {
  return (
    <div className="border-b border-[var(--color-border)] py-4 last:border-b-0">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between text-left font-medium text-lg text-[var(--color-foreground)] py-2 transition-colors hover:text-[var(--color-purple)]"
      >
        <span>{question}</span>
        <span className="ml-4 flex-shrink-0 text-[var(--color-smoke)] transition-transform duration-200">
          <ChevronDown
            className={cn("h-5 w-5 transition-transform duration-300", isOpen && "rotate-180 text-[var(--color-purple)]")}
          />
        </span>
      </button>
      
      {/* Pure CSS grid height transition (bulletproof in Next.js 15 / React 19) */}
      <div
        className={cn(
          "grid transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          isOpen ? "grid-rows-[1fr] opacity-100 mt-2" : "grid-rows-[0fr] opacity-0 pointer-events-none"
        )}
      >
        <div className="overflow-hidden">
          <p className="text-sm leading-relaxed text-[var(--color-smoke)] pb-2 max-w-prose">
            {answer}
          </p>
        </div>
      </div>
    </div>
  );
}

interface AccordionProps {
  items: Array<{ question: string; answer: string; id: string }>;
}

export function Accordion({ items }: AccordionProps) {
  const [openId, setOpenId] = useState<string | null>(null);

  const handleToggle = (id: string) => {
    setOpenId((prev) => (prev === id ? null : id));
  };

  return (
    <div className="w-full divide-y divide-[var(--color-border)]">
      {items.map((item) => (
        <AccordionItem
          key={item.id}
          question={item.question}
          answer={item.answer}
          isOpen={openId === item.id}
          onToggle={() => handleToggle(item.id)}
        />
      ))}
    </div>
  );
}

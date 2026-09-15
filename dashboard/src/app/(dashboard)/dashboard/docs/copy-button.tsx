"use client";

import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";

export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <Button
      variant="ghost"
      className="absolute right-2 top-2 h-8 w-8 p-0 rounded-lg hover:bg-[var(--color-charcoal)]"
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      type="button"
    >
      {copied ? (
        <Check className="h-4 w-4 text-[var(--color-smoke)]" strokeWidth={1.2} />
      ) : (
        <Copy className="h-4 w-4 text-[var(--color-smoke)]" strokeWidth={1.2} />
      )}
    </Button>
  );
}

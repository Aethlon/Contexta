"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Input } from "@/components/ui/input";

export function MemorySearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && query.trim()) {
      router.push(`/dashboard/memories?q=${encodeURIComponent(query.trim())}`);
    }
  }

  return (
    <Input
      className="w-64"
      placeholder="Search memories"
      value={query}
      onChange={(e) => setQuery(e.target.value)}
      onKeyDown={handleKeyDown}
    />
  );
}

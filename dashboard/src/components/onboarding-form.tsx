"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2, User, Palette, Bot, Sliders } from "lucide-react";

export function OnboardingForm({ initialName }: { initialName: string }) {
  const router = useRouter();
  const [name, setName] = useState(initialName || "Jenit");
  const [age, setAge] = useState("");
  const [favoriteColor, setFavoriteColor] = useState("");
  const [companionRole, setCompanionRole] = useState(
    "Autonomous Pair Programmer & Personal Memory Vault"
  );
  const [preferences, setPreferences] = useState(
    "Prefer concise code over long prose. Use modern TypeScript and clean architecture. Do not hallucinate."
  );
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const handleSave = async (skip: boolean = false) => {
    setError(null);
    startTransition(async () => {
      try {
        const payload = skip
          ? { name: initialName || "User" }
          : {
              name,
              age,
              favorite_color: favoriteColor,
              companion_role: companionRole,
              preferences,
            };

        try {
          await fetch("/api/auth/onboarding", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...payload, skip }),
          });
        } catch (fetchErr) {
          console.warn("[onboarding-form] Save request error:", fetchErr);
        }

        document.cookie = "contexta_onboarding_completed=true; path=/; max-age=31536000; SameSite=Lax";
        window.location.href = "/dashboard";
      } catch (err: any) {
        document.cookie = "contexta_onboarding_completed=true; path=/; max-age=31536000; SameSite=Lax";
        window.location.href = "/dashboard";
      }
    });
  };

  return (
    <div className="space-y-4 font-mono">
      {error && (
        <div className="rounded border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
        <div>
          <label className="block text-[11px] text-muted-foreground mb-1.5 flex items-center gap-1.5">
            <User className="h-3 w-3 text-foreground/70" />
            <span>Preferred Name / Handle</span>
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Jenit"
            required
            disabled={isPending}
            className="w-full rounded border border-border/40 bg-card/60 px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground/40 focus:ring-1 focus:ring-foreground/20 transition-all"
          />
        </div>

        <div>
          <label className="block text-[11px] text-muted-foreground mb-1.5 flex items-center gap-1.5">
            <span className="text-xs">🎂</span>
            <span>Age / Birth Year</span>
          </label>
          <input
            type="text"
            value={age}
            onChange={(e) => setAge(e.target.value)}
            placeholder="e.g. 24 or 2000"
            disabled={isPending}
            className="w-full rounded border border-border/40 bg-card/60 px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground/40 focus:ring-1 focus:ring-foreground/20 transition-all"
          />
        </div>
      </div>

      <div>
        <label className="block text-[11px] text-muted-foreground mb-1.5 flex items-center gap-1.5">
          <Palette className="h-3 w-3 text-foreground/70" />
          <span>Favorite Aesthetic or Accent Color</span>
        </label>
        <input
          type="text"
          value={favoriteColor}
          onChange={(e) => setFavoriteColor(e.target.value)}
          placeholder="e.g. Dark ash obsidian, Emerald, Deep navy"
          disabled={isPending}
          className="w-full rounded border border-border/40 bg-card/60 px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground/40 focus:ring-1 focus:ring-foreground/20 transition-all"
        />
      </div>

      <div>
        <label className="block text-[11px] text-muted-foreground mb-1.5 flex items-center gap-1.5">
          <Bot className="h-3 w-3 text-foreground/70" />
          <span>Primary AI Companion Role</span>
        </label>
        <input
          type="text"
          value={companionRole}
          onChange={(e) => setCompanionRole(e.target.value)}
          placeholder="e.g. Autonomous Pair Programmer & Second Brain"
          disabled={isPending}
          className="w-full rounded border border-border/40 bg-card/60 px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground/40 focus:ring-1 focus:ring-foreground/20 transition-all"
        />
      </div>

      <div>
        <label className="block text-[11px] text-muted-foreground mb-1.5 flex items-center gap-1.5">
          <Sliders className="h-3 w-3 text-foreground/70" />
          <span>Personal Habits & Agent Guidelines</span>
        </label>
        <textarea
          rows={2}
          value={preferences}
          onChange={(e) => setPreferences(e.target.value)}
          placeholder="Tell your agents how you like to work, your tech stacks, preferred tone..."
          disabled={isPending}
          className="w-full rounded border border-border/40 bg-card/60 px-3.5 py-2 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground/40 focus:ring-1 focus:ring-foreground/20 transition-all resize-none"
        />
      </div>

      <div className="pt-2 flex flex-col sm:flex-row items-center gap-3">
        <button
          type="button"
          onClick={() => handleSave(false)}
          disabled={isPending}
          className="w-full sm:flex-1 flex items-center justify-center gap-2 rounded bg-foreground hover:bg-foreground/90 active:scale-[0.99] py-2.5 text-xs font-medium text-background transition-all shadow-sm cursor-pointer uppercase tracking-wider disabled:opacity-50"
        >
          {isPending ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span>Saving to Memory Vault...</span>
            </>
          ) : (
            <>
              <span>Encrypt & Initialize Vault</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </>
          )}
        </button>

        <button
          type="button"
          onClick={() => handleSave(true)}
          disabled={isPending}
          className="w-full sm:w-auto px-5 py-2.5 rounded border border-border/40 bg-transparent hover:bg-secondary/60 text-xs text-muted-foreground hover:text-foreground transition-all cursor-pointer disabled:opacity-50"
        >
          Skip for now
        </button>
      </div>
    </div>
  );
}

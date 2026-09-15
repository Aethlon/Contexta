"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { signOut } from "next-auth/react";
import { Trash2, AlertTriangle, Loader2, Eye, EyeOff } from "lucide-react";

export function EmergencyResetForm() {
  const router = useRouter();
  const [email, setEmail] = useState("User@aethlon.xyz");
  const [confirmation, setConfirmation] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    if (confirmation.trim().toUpperCase() !== "WIPE") {
      setError("You must type 'WIPE' to confirm permanent cryptographic shredding.");
      return;
    }
    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    startTransition(async () => {
      try {
        const res = await fetch("/api/auth/emergency-wipe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email,
            confirmation: "WIPE",
            new_password: newPassword,
          }),
        });

        const data = await res.json();
        if (!res.ok) {
          setError(data.detail || "Failed to perform emergency wipe.");
          return;
        }

        try {
          await signOut({ redirect: false });
        } catch {
          // Ignore
        }

        router.push(
          "/sign-in?success=" +
            encodeURIComponent(
              "Vault shredded and password reset. Authenticate with your new password."
            )
        );
      } catch (err: any) {
        setError(err?.message || "Unable to reach server.");
      }
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3.5 font-mono">
      {error && (
        <div className="flex items-start gap-3 rounded border border-red-500/30 bg-red-500/20 p-3 text-xs text-red-300">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <div>
        <label className="block text-[11px] text-muted-foreground mb-1">
          Account Email
        </label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="User@aethlon.xyz"
          required
          disabled={isPending}
          className="w-full rounded border border-border/40 bg-card/60 px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-red-500/40 focus:ring-1 focus:ring-red-500/20 transition-all"
        />
      </div>

      <div>
        <label className="block text-[11px] text-red-400 font-medium mb-1">
          Type &ldquo;WIPE&rdquo; to Confirm
        </label>
        <input
          id="confirmation"
          type="text"
          value={confirmation}
          onChange={(e) => setConfirmation(e.target.value)}
          placeholder="Type WIPE in all caps"
          required
          autoComplete="off"
          disabled={isPending}
          className="w-full rounded border border-red-500/40 bg-red-950/20 px-3.5 py-2.5 text-xs text-red-200 placeholder:text-red-400/40 outline-none focus:border-red-500 focus:ring-1 focus:ring-red-500/30 transition-all font-bold tracking-widest uppercase"
        />
      </div>

      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="block text-[11px] text-muted-foreground">
            New Master Password (min 8 chars)
          </label>
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="text-[10px] text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
          >
            {showPassword ? (
              <>
                <EyeOff className="h-3 w-3" />
                <span>Hide</span>
              </>
            ) : (
              <>
                <Eye className="h-3 w-3" />
                <span>Show</span>
              </>
            )}
          </button>
        </div>
        <input
          id="newPassword"
          type={showPassword ? "text" : "password"}
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          placeholder="Set new master password"
          required
          disabled={isPending}
          className="w-full rounded border border-border/40 bg-card/60 px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground/40 focus:ring-1 focus:ring-foreground/20 transition-all"
        />
      </div>

      <div>
        <label className="block text-[11px] text-muted-foreground mb-1">
          Confirm New Master Password
        </label>
        <input
          id="confirmPassword"
          type={showPassword ? "text" : "password"}
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          placeholder="Confirm new master password"
          required
          disabled={isPending}
          className="w-full rounded border border-border/40 bg-card/60 px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground/40 focus:ring-1 focus:ring-foreground/20 transition-all"
        />
      </div>

      <div className="pt-2">
        <button
          type="submit"
          disabled={isPending}
          className="w-full flex items-center justify-center gap-2 rounded bg-red-600 hover:bg-red-500 active:scale-[0.99] py-2.5 text-xs font-semibold text-white transition-all shadow-sm cursor-pointer uppercase tracking-wider disabled:opacity-50"
        >
          {isPending ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span>Shredding Vault & Wiping Records...</span>
            </>
          ) : (
            <>
              <Trash2 className="h-3.5 w-3.5" />
              <span>Shred Vault & Reset Credentials</span>
            </>
          )}
        </button>
      </div>
    </form>
  );
}

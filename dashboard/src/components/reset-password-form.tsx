"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { signOut } from "next-auth/react";
import { ShieldAlert, ArrowRight, Loader2, Eye, EyeOff } from "lucide-react";

export function ResetPasswordForm({ defaultEmail }: { defaultEmail: string }) {
  const router = useRouter();
  const [email] = useState(defaultEmail || "User@aethlon.xyz");
  const [currentPassword, setCurrentPassword] = useState("password1234");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (newPassword === currentPassword) {
      setError("New password must be different from current default password.");
      return;
    }

    startTransition(async () => {
      try {
        const res = await fetch("/api/auth/reset-password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email,
            current_password: currentPassword,
            new_password: newPassword,
          }),
        });

        const data = await res.json();
        if (!res.ok) {
          setError(data.detail || "Failed to update master password.");
          return;
        }

        // Invalidate temporary setup session
        try {
          await signOut({ redirect: false });
        } catch {
          // Ignore
        }

        router.push(
          "/sign-in?success=" +
            encodeURIComponent(
              "Master password updated successfully. Sign in with your new credentials."
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
        <div className="flex items-start gap-3 rounded border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400">
          <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5" />
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
          readOnly
          className="w-full rounded border border-border/40 bg-card/50 px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground outline-none cursor-default opacity-80"
        />
      </div>

      <div>
        <label className="block text-[11px] text-muted-foreground mb-1">
          Current Default Password
        </label>
        <input
          id="currentPassword"
          type="password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          required
          placeholder="e.g. password1234"
          disabled={isPending}
          className="w-full rounded border border-border/40 bg-card/60 px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground/40 focus:ring-1 focus:ring-foreground/20 transition-all"
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
          required
          placeholder="Enter new master password"
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
          required
          placeholder="Re-enter new master password"
          disabled={isPending}
          className="w-full rounded border border-border/40 bg-card/60 px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground/40 focus:ring-1 focus:ring-foreground/20 transition-all"
        />
      </div>

      <div className="pt-2">
        <button
          type="submit"
          disabled={isPending}
          className="w-full flex items-center justify-center gap-2 rounded bg-foreground hover:bg-foreground/90 active:scale-[0.99] py-2.5 text-xs font-medium text-background transition-all shadow-sm cursor-pointer uppercase tracking-wider disabled:opacity-50"
        >
          {isPending ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span>Updating Master Credentials...</span>
            </>
          ) : (
            <>
              <span>Update & Re-Authenticate</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </>
          )}
        </button>
      </div>
    </form>
  );
}

"use client";

import { useState, useTransition } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { signIn } from "next-auth/react";
import { Mail, AlertCircle, Loader2, Eye, EyeOff } from "lucide-react";

export function SovereignSignInForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlError = searchParams.get("error");

  const [email, setEmail] = useState("User@aethlon.xyz");
  const [password, setPassword] = useState("password1234");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(urlError);
  const [isPending, startTransition] = useTransition();

  const [isEngineOffline, setIsEngineOffline] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);

  const handleLaunchEngine = async () => {
    setIsLaunching(true);
    try {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke("launch_contexta_engine");
      } catch {
        await fetch("/api/system/engine", { method: "POST" });
      }
      setError("Engine launch initiated. Waiting for node to come online...");
    } catch {
      setError("Failed to trigger engine launch. Please run .\\start.ps1 in PowerShell.");
    } finally {
      setTimeout(() => setIsLaunching(false), 5000);
    }
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setIsEngineOffline(false);

    startTransition(async () => {
      try {
        // Quick probe to check if engine is responsive
        const engineCheck = await fetch("/api/system/engine").then(r => r.json()).catch(() => ({ online: false }));
        if (!engineCheck.online) {
          setIsEngineOffline(true);
          setError("Sovereign node backend (:8000) is offline.");
          return;
        }

        const res = await signIn("credentials", {
          email,
          password,
          redirect: false,
        });

        if (res?.error) {
          setError(
            res.error === "CredentialsSignin"
              ? "Invalid master password or credentials."
              : res.error
          );
          return;
        }

        // On successful authentication, navigate to root to resolve mandatory reset/onboarding/dashboard
        router.push("/");
        router.refresh();
      } catch (err: any) {
        setError(err?.message || "Failed to authenticate with sovereign node.");
      }
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3 font-mono">
      {/* Error Banner */}
      {error && (
        <div className="mb-4 rounded border border-red-500/30 bg-red-500/10 p-3.5 text-xs text-red-400 space-y-2">
          <div className="flex items-start gap-2.5">
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="block font-medium">{error}</span>
              {isEngineOffline && (
                <span className="block text-[11px] text-muted-foreground">
                  The Contexta Brain backend container (port 8000) is not responding. Start it to authenticate.
                </span>
              )}
            </div>
          </div>
          {isEngineOffline && (
            <button
              type="button"
              onClick={handleLaunchEngine}
              disabled={isLaunching}
              className="w-full py-2 px-3 rounded bg-amber-500/20 border border-amber-500/40 text-amber-300 hover:bg-amber-500/30 text-xs font-mono transition-all flex items-center justify-center gap-2 cursor-pointer"
            >
              {isLaunching ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span>Initiating Background Launch...</span>
                </>
              ) : (
                <span>Launch Contexta Engine in Background &rarr;</span>
              )}
            </button>
          )}
        </div>
      )}

      <div>
        <label className="block text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
          Account Email
        </label>
        <input
          id="email"
          name="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email address"
          required
          disabled={isPending}
          className="w-full rounded border border-border/40 bg-card/60 px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground/40 focus:ring-1 focus:ring-foreground/20 transition-all"
        />
      </div>

      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="block text-[10px] uppercase tracking-wider text-muted-foreground">
            Master Password
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
          id="password"
          name="password"
          type={showPassword ? "text" : "password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Master Password"
          required
          disabled={isPending}
          className="w-full rounded border border-border/40 bg-card/60 px-3.5 py-2.5 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-foreground/40 focus:ring-1 focus:ring-foreground/20 transition-all"
        />
      </div>

      <button
        type="submit"
        disabled={isPending}
        className="w-full flex items-center justify-center gap-2 rounded bg-foreground hover:bg-foreground/90 active:scale-[0.99] py-2.5 text-xs font-mono font-medium text-background transition-all shadow-sm cursor-pointer mt-4 uppercase tracking-wider disabled:opacity-50"
      >
        {isPending ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            <span>Authenticating Vault...</span>
          </>
        ) : (
          <>
            <Mail className="h-3.5 w-3.5" />
            <span>Sign In to Sovereign Node</span>
          </>
        )}
      </button>
    </form>
  );
}

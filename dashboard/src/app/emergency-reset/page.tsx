import Link from "next/link";
import { AlertTriangle, ArrowLeft, Lock } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { ContextaMark } from "@/components/contexta-logo";
import { EmergencyResetForm } from "@/components/emergency-reset-form";

export default async function EmergencyResetPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const params = await searchParams;

  return (
    <main className="relative min-h-screen bg-background text-foreground flex items-center justify-center p-4 sm:p-6 antialiased selection:bg-zinc-800 selection:text-zinc-200">
      {/* Top right theme toggle */}
      <div className="absolute top-5 right-6 z-20 flex items-center gap-4">
        <ThemeToggle />
      </div>

      {/* Top left back to sign-in */}
      <div className="absolute top-5 left-6 z-20">
        <Link
          href="/sign-in"
          className="inline-flex items-center gap-1.5 text-xs font-mono text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Sign In
        </Link>
      </div>

      {/* Emergency Wipe Card */}
      <div className="w-full max-w-md rounded-xl border border-red-500/30 bg-card/80 backdrop-blur-xl p-8 sm:p-10 shadow-2xl relative z-10 font-mono">
        {/* Brand Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2.5">
            <div className="relative flex items-center justify-center w-8 h-8 rounded border border-border/40 bg-secondary/60 text-foreground">
              <ContextaMark className="size-5" />
            </div>
            <span className="text-sm uppercase tracking-widest text-foreground flex items-center">
              contexta<span className="text-[10px] text-muted-foreground ml-1 font-normal">™</span>
            </span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded bg-red-500/10 border border-red-500/30 text-red-400 font-semibold tracking-wider uppercase">
            Emergency Vault Wipe
          </span>
        </div>

        {/* Warning Banner */}
        <div className="rounded border border-red-500/30 bg-red-500/10 p-3.5 text-xs text-red-300 mb-6 space-y-1.5">
          <div className="flex items-center gap-2 font-semibold text-red-400">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>Permanent Cryptographic Shredding</span>
          </div>
          <p className="text-[11px] leading-relaxed text-red-300/90">
            Your memories are encrypted on disk. If you forgot your master password, your vault cannot be recovered. Proceeding will permanently purge all memories, vector embeddings, and knowledge graph links for this account.
          </p>
        </div>

        {/* Error message */}
        {params.error && (
          <div className="mb-6 flex items-start gap-3 rounded border border-red-500/30 bg-red-500/20 p-3 text-xs text-red-300">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{params.error}</span>
          </div>
        )}

        {/* Form */}
        <EmergencyResetForm />

        <div className="mt-5 text-center">
          <Link
            href="/sign-in"
            className="text-[11px] text-muted-foreground hover:text-foreground transition-colors inline-flex items-center gap-1"
          >
            <Lock className="h-3 w-3" />
            Remember your credentials? Return to sign in
          </Link>
        </div>
      </div>
    </main>
  );
}

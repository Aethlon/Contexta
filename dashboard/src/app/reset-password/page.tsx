import { KeyRound, ShieldAlert, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { ThemeToggle } from "@/components/theme-toggle";
import { ContextaMark } from "@/components/contexta-logo";
import { resolveOperatorIdentity } from "@/lib/dashboard-identity";
import { ResetPasswordForm } from "@/components/reset-password-form";

export const dynamic = "force-dynamic";

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; success?: string }>;
}) {
  const params = await searchParams;
  const identity = await resolveOperatorIdentity();
  const defaultEmail = identity.email ?? "";

  return (
    <main className="relative min-h-screen bg-background text-foreground flex items-center justify-center p-4 sm:p-6 antialiased selection:bg-zinc-800 selection:text-zinc-200">
      {/* Top right theme toggle */}
      <div className="absolute top-5 right-6 z-20 flex items-center gap-4">
        <ThemeToggle />
      </div>

      {/* Center Auth Card */}
      <div className="w-full max-w-md rounded-lg border border-border bg-card  p-8 sm:p-10 shadow-2xl relative z-10 font-mono">
        {/* Brand Header */}
        <div className="flex items-center gap-2.5 mb-8">
          <div className="relative flex items-center justify-center w-8 h-8 rounded border border-border bg-secondary/60 text-foreground">
            <ContextaMark className="size-5" />
          </div>
          <span className="text-sm uppercase tracking-widest text-foreground flex items-center">
            contexta
          </span>
        </div>

        {/* Title */}
        <div className="space-y-2 mb-6">
          <h1 className="text-xl sm:text-2xl font-normal tracking-tight text-foreground flex items-center gap-2">
            <KeyRound className="h-5 w-5 tone-amber" />
            Change Master Password
          </h1>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Replaces the account password used for credential sign-in. This is
            only consulted when{" "}
            <code className="text-foreground">CONTEXTA_DASHBOARD_AUTH=on</code>;
            with authentication off, the console reaches the API with a
            bootstrap API key instead.
          </p>
        </div>

        {/* Alert banners */}
        {params.error && (
          <div className="mb-6 flex items-start gap-3 rounded border border-red-500/30 bg-red-500/10 p-3 text-xs tone-red">
            <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{params.error}</span>
          </div>
        )}
        {params.success && (
          <div className="mb-6 flex items-start gap-3 rounded border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs tone-green">
            <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{params.success}</span>
          </div>
        )}

        {/* Form */}
        <ResetPasswordForm defaultEmail={defaultEmail} />

        <p className="mt-5 text-center text-[10px] text-muted-foreground leading-normal">
          <Link href="/dashboard" className="underline underline-offset-2 hover:text-foreground">
            Back to the console
          </Link>
        </p>
      </div>
    </main>
  );
}

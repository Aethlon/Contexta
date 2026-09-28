import Link from "next/link";
import { ArrowRight, ShieldOff } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { ContextaMark } from "@/components/contexta-logo";
import { SovereignSignInForm } from "@/components/sovereign-sign-in-form";
import { isAuthRequired } from "@/lib/dashboard-identity";
import { Suspense } from "react";

export const dynamic = "force-dynamic";

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; success?: string }>;
}) {
  const params = await searchParams;
  const authRequired = isAuthRequired();

  // Default configuration: page auth is off. Rendering the credentials form here
  // would be a dead end, so say so plainly and point at the console instead.
  if (!authRequired) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background p-6 text-foreground">
        <div className="absolute right-6 top-5">
          <ThemeToggle />
        </div>
        <div className="w-full max-w-lg space-y-6 rounded-lg border border-border bg-card p-8 font-mono">
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 items-center justify-center rounded border border-border bg-secondary/60">
              <ContextaMark className="size-5" />
            </div>
            <span className="text-sm uppercase tracking-widest">contexta</span>
          </div>

          <div className="inline-flex items-center gap-1.5 rounded border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[11px] tone-amber">
            <ShieldOff className="size-3.5" />
            <span>Authentication is disabled</span>
          </div>

          <div className="space-y-2">
            <h1 className="text-xl font-normal tracking-tight">
              There is no sign-in here
            </h1>
            <p className="text-xs leading-relaxed text-muted-foreground">
              This is a self-hosted, single-operator console, so page
              authentication ships <span className="text-foreground">off</span>.
              The console authenticates to the Python API with a bootstrap API
              key, and anyone who can reach this port has the same access as the
              operator.
            </p>
          </div>

          <div className="space-y-1.5 rounded border border-border bg-secondary/25 p-3 text-[11px] text-muted-foreground">
            <p className="text-foreground">To require a sign-in</p>
            <p>
              Set <code className="font-mono text-foreground">CONTEXTA_DASHBOARD_AUTH=on</code>{" "}
              in the dashboard&apos;s environment and restart it. The credentials
              form on this page then becomes live, and the organization the
              console acts on comes from the signed-in account. See{" "}
              <code className="font-mono text-foreground">dashboard/README.md</code>.
            </p>
          </div>

          <Link href="/dashboard" className="nb-btn nb-btn-primary w-full justify-center">
            <span>Open the console</span>
            <ArrowRight className="size-3.5" />
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="relative min-h-screen bg-background text-foreground flex flex-col lg:flex-row antialiased selection:bg-zinc-800 selection:text-zinc-200">
      {/* Top right theme toggle */}
      <div className="absolute top-5 right-6 z-20 flex items-center gap-4">
        <ThemeToggle />
      </div>

      {/* Left Column: Minimal Auth Form */}
      <div className="w-full lg:w-[48%] xl:w-[44%] flex flex-col justify-between p-6 sm:p-12 lg:p-16 xl:p-20 z-10">
        <div>
          {/* Brand Header */}
          <div className="flex items-center gap-2.5 mb-12">
            <div className="relative flex items-center justify-center w-8 h-8 rounded border border-border bg-secondary/60 text-foreground">
              <ContextaMark className="size-5" />
            </div>
            <span className="text-sm font-mono uppercase tracking-widest text-foreground flex items-center">
              contexta
            </span>
          </div>

          {/* Form Header */}
          <div className="space-y-2 mb-8 font-mono">
            <h1 className="text-2xl sm:text-3xl font-normal tracking-tight text-foreground">
              Sign in to Console
            </h1>
            <p className="text-xs text-muted-foreground font-normal">
              Enter your credentials to access the memory control plane.
            </p>
          </div>

          {/* Status Banners */}
          {params.error && (
            <div className="mb-6 flex items-start gap-3 rounded border border-red-500/30 bg-red-500/10 p-3.5 text-xs font-mono tone-red">
              <span>{params.error}</span>
            </div>
          )}
          {params.success && (
            <div className="mb-6 flex items-start gap-3 rounded border border-emerald-500/30 bg-emerald-500/10 p-3.5 text-xs font-mono tone-green">
              <span>{params.success}</span>
            </div>
          )}

          {/* Sovereign Auth Form */}
          <Suspense fallback={<div className="h-40 rounded border border-border bg-card/30 animate-pulse" />}>
            <SovereignSignInForm />
          </Suspense>

          {/* Emergency Reset & Switch link */}
          <div className="mt-6 flex flex-col gap-2 text-center text-xs font-mono text-muted-foreground">
            <div>
              Forgot master password?{" "}
              <Link
                href="/emergency-reset"
                className="tone-red hover:text-destructive hover:underline underline-offset-4 transition-colors font-normal"
              >
                Emergency Wipe & Reset
              </Link>
            </div>
            <div>
              New deployment?{" "}
              <Link
                href="/sign-up"
                className="text-foreground hover:underline underline-offset-4 transition-colors font-normal"
              >
                Create initial user
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Right Column: what re-enabling auth actually means */}
      <div className="w-full lg:w-[52%] xl:w-[56%] p-3 sm:p-5 lg:p-6 flex items-center justify-center">
        <div className="relative w-full h-auto lg:h-[calc(100vh-3rem)] max-h-[520px] rounded-lg overflow-y-auto border border-border shadow-2xl flex flex-col items-center justify-center p-6 sm:p-10 bg-card font-mono">
          <div className="relative z-10 flex flex-col items-center max-w-[440px] w-full text-center space-y-5">
            <div className="flex items-center gap-2 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-[10px] tone-amber">
              <ShieldOff className="size-3.5" />
              <span>CONTEXTA_DASHBOARD_AUTH=on</span>
            </div>
            <h2 className="text-base font-medium text-foreground">
              Page authentication is enabled
            </h2>
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              The dashboard now gates every page behind a NextAuth v5 credentials
              session. The session&apos;s organization and user ids are what the
              console sends to the Python API, so the console is scoped to the
              organization you signed in as.
            </p>
            <ul className="w-full space-y-2 text-left text-[11px] text-muted-foreground">
              <li className="flex gap-2">
                <span className="tone-green shrink-0">+</span>
                <span>
                  Use this when the console is reachable by more than one person,
                  or from anywhere but localhost.
                </span>
              </li>
              <li className="flex gap-2">
                <span className="tone-red shrink-0">&minus;</span>
                <span>
                  An account must exist in the API first. Create one at{" "}
                  <Link href="/sign-up" className="text-foreground underline">
                    /sign-up
                  </Link>
                  .
                </span>
              </li>
            </ul>
            <Link href="/dashboard" className="nb-btn nb-btn-secondary">
              <span>Continue to console</span>
              <ArrowRight className="size-3.5" />
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}

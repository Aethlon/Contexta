import Link from "next/link";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { ContextaMark } from "@/components/contexta-logo";
import { SovereignSignInForm } from "@/components/sovereign-sign-in-form";
import { Suspense } from "react";

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; success?: string }>;
}) {
  const params = await searchParams;

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
            <div className="relative flex items-center justify-center w-8 h-8 rounded border border-border/40 bg-secondary/60 text-foreground">
              <ContextaMark className="size-5" />
            </div>
            <span className="text-sm font-mono uppercase tracking-widest text-foreground flex items-center">
              contexta<span className="text-[10px] text-muted-foreground font-mono ml-1 font-normal">™</span>
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
            <div className="mb-6 flex items-start gap-3 rounded border border-red-500/30 bg-red-500/10 p-3.5 text-xs font-mono text-red-400">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <span>{params.error}</span>
            </div>
          )}
          {params.success && (
            <div className="mb-6 flex items-start gap-3 rounded border border-emerald-500/30 bg-emerald-500/10 p-3.5 text-xs font-mono text-emerald-400">
              <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
              <span>{params.success}</span>
            </div>
          )}

          {/* Default Credentials Callout */}
          <div className="mb-6 rounded border border-border/40 bg-secondary/40 p-3 text-xs font-mono text-muted-foreground flex flex-col gap-1.5">
            <div className="flex items-center justify-between text-[11px] text-foreground font-medium">
              <span>Sovereign Default Instance</span>
              <span className="text-[10px] text-emerald-400 uppercase tracking-widest font-mono">Offline-First</span>
            </div>
            <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground">
              <span>Login: <span className="text-foreground select-all">User@aethlon.xyz</span></span>
              <span>Pass: <span className="text-foreground select-all">password1234</span></span>
            </div>
          </div>

          {/* Sovereign Auth Form */}
          <Suspense fallback={<div className="h-40 rounded border border-border/20 bg-card/30 animate-pulse" />}>
            <SovereignSignInForm />
          </Suspense>

          {/* Emergency Reset & Switch link */}
          <div className="mt-6 flex flex-col gap-2 text-center text-xs font-mono text-muted-foreground">
            <div>
              Forgot master password?{" "}
              <Link
                href="/emergency-reset"
                className="text-red-400 hover:text-red-300 hover:underline underline-offset-4 transition-colors font-normal"
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

        {/* Footer info */}
        <div className="pt-8 text-center lg:text-left font-mono">
          <p className="text-[11px] text-muted-foreground font-light">
            By continuing, you agree to our{" "}
            <a href="#" className="text-muted-foreground hover:text-foreground transition-colors underline underline-offset-2">
              Terms of Service
            </a>{" "}
            and{" "}
            <a href="#" className="text-muted-foreground hover:text-foreground transition-colors underline underline-offset-2">
              Privacy Policy
            </a>
            .
          </p>
        </div>
      </div>

      {/* Right Column: Frame with Testimonial */}
      <div className="w-full lg:w-[52%] xl:w-[56%] p-3 sm:p-5 lg:p-6 flex items-center justify-center">
        <div className="relative w-full h-[520px] lg:h-[calc(100vh-3rem)] rounded-xl overflow-hidden border border-border/40 shadow-2xl flex flex-col items-center justify-center p-6 sm:p-10 bg-card/50">
          {/* Background Image with muted dark overlay */}
          <div
            className="absolute inset-0 bg-cover bg-center transition-transform duration-1000 scale-105 opacity-40"
            style={{ backgroundImage: "url('/auth-meadow.jpg')" }}
          />

          {/* Soft atmospheric gradient layer */}
          <div className="absolute inset-0 bg-gradient-to-t from-background via-background/60 to-transparent pointer-events-none" />

          {/* Floating Testimonial Section */}
          <div className="relative z-10 flex flex-col items-center max-w-[440px] w-full text-center space-y-4">
            {/* Overlapping User Avatars */}
            <div className="flex items-center -space-x-2.5 drop-shadow-md">
              <div className="w-9 h-9 rounded-full border-2 border-border overflow-hidden bg-secondary">
                <img
                  src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=120&h=120&fit=crop&crop=faces"
                  alt="Avatar 1"
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="w-9 h-9 rounded-full border-2 border-border overflow-hidden bg-secondary z-10">
                <img
                  src="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=120&h=120&fit=crop&crop=faces"
                  alt="Avatar 2"
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="w-9 h-9 rounded-full border-2 border-border overflow-hidden bg-secondary z-20">
                <img
                  src="https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=120&h=120&fit=crop&crop=faces"
                  alt="Avatar 3"
                  className="w-full h-full object-cover"
                />
              </div>
            </div>

            {/* Testimonial Card */}
            <div className="w-full rounded border border-border/40 bg-card/90 text-foreground backdrop-blur-xl p-6 sm:p-7 shadow-[0_20px_50px_rgba(0,0,0,0.4)] text-left font-mono">
              <p className="text-xs sm:text-sm font-normal leading-relaxed text-foreground mb-2.5">
                &ldquo;We just ditched RAG completely and went memory only through Contexta.&rdquo;
              </p>
              <p className="text-[11px] text-muted-foreground font-normal leading-relaxed mb-5">
                Reduced avg response time from 40s → 12s. Using about 40–50% fewer tokens.
              </p>

              {/* Author */}
              <div className="flex items-center gap-3 pt-3 border-t border-border/40">
                <img
                  src="https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=100&h=100&fit=crop&crop=faces"
                  alt="Armin Daryabegi"
                  className="w-8 h-8 rounded-full object-cover border border-border/40"
                />
                <div>
                  <h4 className="text-xs font-medium text-foreground leading-tight">
                    Armin Daryabegi
                  </h4>
                  <p className="text-[10px] text-muted-foreground">Founder, Chatmin</p>
                </div>
              </div>
            </div>

            {/* Floating Metric Pills */}
            <div className="flex flex-wrap items-center justify-center gap-2 pt-1 font-mono">
              <span className="inline-flex items-center rounded border border-border/40 bg-secondary/60 backdrop-blur-md px-3 py-1 text-[10px] font-normal text-muted-foreground shadow-sm">
                100B+ tokens/mo
              </span>
              <span className="inline-flex items-center rounded border border-border/40 bg-secondary/60 backdrop-blur-md px-3 py-1 text-[10px] font-normal text-muted-foreground shadow-sm">
                &lt;300ms p95 recall
              </span>
              <span className="inline-flex items-center rounded border border-border/40 bg-secondary/60 backdrop-blur-md px-3 py-1 text-[10px] font-normal text-muted-foreground shadow-sm">
                Zero hallucination drift
              </span>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}

import Link from "next/link";
import { ArrowRight, Brain, CheckCircle2, ShieldCheck, Sparkles, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { signInAction, signInWithGoogleAction, signInWithGitHubAction } from "@/app/actions";
import { ThemeToggle } from "@/components/theme-toggle";

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; success?: string }>;
}) {
  const params = await searchParams;

  return (
    <main className="relative flex min-h-screen items-center justify-center bg-[var(--color-abyss)] px-4 py-16 sm:px-6 lg:px-8">
      <div className="grid w-full max-w-5xl gap-12 lg:grid-cols-[1fr_0.95fr] items-center">
        {/* Left Side Content */}
        <div className="space-y-8">
          <div className="inline-flex">
            <Badge className="text-xs">
              <Sparkles className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.2} /> Secure access to your memory workspace
            </Badge>
          </div>
          <h1 className="text-4xl font-light tracking-tighter sm:text-5xl text-[var(--color-ghost)]">
            Welcome back to your agent memory layer.
          </h1>
          <p className="text-base font-light leading-7 text-[var(--color-smoke)]">
            Sign in to inspect your memory flows, manage API keys, and keep every retrieval grounded in your organization’s context.
          </p>
          <div className="space-y-4">
            {[
              "Tenant-safe access for every workspace",
              "Fast retrieval and policy controls",
              "Simple onboarding for teams and developers",
            ].map((item) => (
              <div key={item} className="flex items-center gap-3 text-sm text-[var(--color-ghost)] font-light">
                <CheckCircle2 className="h-4 w-4 text-[var(--color-smoke)]" strokeWidth={1.2} />
                {item}
              </div>
            ))}
          </div>
          <div className="rounded-2xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6">
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--color-charcoal)] text-[var(--color-ghost)]">
                <ShieldCheck className="h-5 w-5" strokeWidth={1.2} />
              </div>
              <div className="space-y-1">
                <h2 className="text-sm font-normal text-[var(--color-ghost)]">Protected by organization scoping</h2>
                <p className="text-xs font-light text-[var(--color-smoke)] leading-relaxed">Your data stays isolated and retrieval stays precise.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Right Side Form Card */}
        <div className="space-y-4">
          <div className="flex justify-end pr-2">
            <ThemeToggle />
          </div>
          <Card className="w-full border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] shadow-[0_24px_50px_rgba(0,0,0,0.22),inset_0_1px_0_0_rgba(255,255,255,0.02)]">
            <CardHeader className="pb-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-charcoal)] text-[var(--color-ghost)]">
                  <Brain className="h-5 w-5" strokeWidth={1.2} />
                </div>
                <div>
                  <CardTitle className="text-lg">Sign in</CardTitle>
                  <CardDescription>Access your contexta dashboard.</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {params.error ? (
                <div className="flex items-start gap-3 border-b border-[var(--color-graphite)]/30 pb-4">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0 text-red-400" strokeWidth={1.2} />
                  <span className="text-sm font-light text-red-400">{params.error}</span>
                </div>
              ) : null}
              {params.success ? (
                <div className="flex items-start gap-3 border-b border-[var(--color-graphite)]/30 pb-4">
                  <span className="text-sm font-light text-[var(--color-smoke)]">{params.success}</span>
                </div>
              ) : null}

              <form action={signInAction} className="space-y-5">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" name="email" placeholder="you@company.com" type="email" required />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="password">Password</Label>
                  <Input id="password" name="password" placeholder="At least 8 characters" type="password" required />
                </div>
                <Button className="w-full mt-2" type="submit">
                  Continue <ArrowRight className="h-4 w-4" strokeWidth={1.2} />
                </Button>
              </form>

              <div className="relative py-2">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t border-[var(--color-graphite)]/30" />
                </div>
                <div className="relative flex justify-center text-[10px] font-mono tracking-widest uppercase">
                  <span className="bg-[var(--color-ash)] px-3 text-[var(--color-smoke)]">Or continue with</span>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <form action={signInWithGoogleAction}>
                  <Button className="w-full" type="submit" variant="outline">
                    <svg className="h-4 w-4 mr-1" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="currentColor"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="currentColor" opacity="0.8"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="currentColor" opacity="0.6"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="currentColor" opacity="0.7"/></svg>
                    Google
                  </Button>
                </form>
                <form action={signInWithGitHubAction}>
                  <Button className="w-full" type="submit" variant="outline">
                    <svg className="h-4 w-4 mr-1" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>
                    GitHub
                  </Button>
                </form>
              </div>

              <p className="text-center text-sm font-light text-[var(--color-smoke)] pt-2">
                New here? <Link className="font-normal text-[var(--color-ghost)] underline decoration-[var(--color-graphite)] hover:text-white transition-colors" href="/sign-up">Create an account</Link>
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </main>
  );
}

// Minimal Badge helper that works in RSC
function Badge({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-md border border-[var(--color-graphite)] bg-[var(--color-ash)] px-2 py-0.5 text-[10px] font-mono tracking-widest uppercase text-[var(--color-smoke)] ${className}`}>
      {children}
    </span>
  );
}

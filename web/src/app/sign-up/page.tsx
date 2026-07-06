"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { signUpAction } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ArrowRight, Brain, CheckCircle2, Sparkles } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";

export default function SignUpPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const result = await signUpAction(form);
    setPending(false);
    if (result?.error) {
      setError(result.error);
    } else {
      router.push("/sign-in?success=Account created successfully. Please sign in.");
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center bg-[var(--color-abyss)] px-4 py-16 sm:px-6 lg:px-8">
      <div className="grid w-full max-w-5xl gap-12 lg:grid-cols-[1fr_0.95fr] items-center">
        {/* Left Side Content */}
        <div className="space-y-8">
          <div className="inline-flex">
            <Badge className="text-xs">
              <Sparkles className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.2} /> Bring memory to your product
            </Badge>
          </div>
          <h1 className="text-4xl font-light tracking-tighter sm:text-5xl text-[var(--color-ghost)]">
            Create your account and launch smarter agents.
          </h1>
          <p className="text-base font-light leading-7 text-[var(--color-smoke)]">
            Start with a polished memory layer for conversations, preferences, and durable context that your agents can reuse.
          </p>
          <div className="space-y-4">
            {[
              "Fast setup with secure authentication",
              "Built-in retrieval and policy controls",
              "A clean foundation for teams and products",
            ].map((item) => (
              <div key={item} className="flex items-center gap-3 text-sm text-[var(--color-ghost)] font-light">
                <CheckCircle2 className="h-4 w-4 text-[var(--color-smoke)]" strokeWidth={1.2} />
                {item}
              </div>
            ))}
          </div>
          <div className="rounded-2xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6">
            <p className="text-sm font-light text-[var(--color-smoke)] leading-relaxed">
              Ideal for product teams building copilots, assistants, and support experiences.
            </p>
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
                  <CardTitle className="text-lg">Create account</CardTitle>
                  <CardDescription>Start using the contexta dashboard.</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {error ? (
                <div className="flex items-start gap-3 border-b border-[var(--color-graphite)]/30 pb-4">
                  <span className="text-sm font-light text-red-400">{error}</span>
                </div>
              ) : null}

              <form className="space-y-5" onSubmit={onSubmit}>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" name="email" placeholder="you@company.com" type="email" required />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="password">Password</Label>
                  <Input id="password" name="password" placeholder="At least 8 characters" type="password" required />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="confirmPassword">Confirm password</Label>
                  <Input id="confirmPassword" name="confirmPassword" placeholder="Repeat password" type="password" required />
                </div>
                <Button className="w-full mt-2 animate-none" disabled={pending} type="submit">
                  {pending ? (
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent mr-1" />
                  ) : null}
                  Create account <ArrowRight className="h-4 w-4" strokeWidth={1.2} />
                </Button>
              </form>
              <p className="text-center text-sm font-light text-[var(--color-smoke)] pt-2">
                Already have an account? <Link className="font-normal text-[var(--color-ghost)] underline decoration-[var(--color-graphite)] hover:text-white transition-colors" href="/sign-in">Sign in</Link>
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </main>
  );
}

// Minimal Badge helper
function Badge({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-md border border-[var(--color-graphite)] bg-[var(--color-ash)] px-2 py-0.5 text-[10px] font-mono tracking-widest uppercase text-[var(--color-smoke)] ${className}`}>
      {children}
    </span>
  );
}

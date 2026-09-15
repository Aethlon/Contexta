import { Bot, ShieldCheck } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { ContextaMark } from "@/components/contexta-logo";
import { getSession } from "@/lib/auth-helpers";
import { OnboardingChat } from "@/components/onboarding-chat";

export default async function OnboardingPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const params = await searchParams;
  const session = await getSession();
  const initialName = session?.user?.name || "Jenit";

  return (
    <main className="relative min-h-screen bg-background text-foreground flex flex-col items-center justify-center p-4 sm:p-8 antialiased selection:bg-zinc-800 selection:text-zinc-200">
      {/* Top right theme toggle */}
      <div className="absolute top-5 right-6 z-20 flex items-center gap-4">
        <ThemeToggle />
      </div>

      {/* Onboarding Container */}
      <div className="w-full max-w-5xl relative z-10 font-mono space-y-6">
        {/* Brand Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="relative flex items-center justify-center w-8 h-8 rounded border border-border/40 bg-secondary/60 text-foreground">
              <ContextaMark className="size-5" />
            </div>
            <span className="text-sm uppercase tracking-widest text-foreground flex items-center">
              contexta<span className="text-[10px] text-muted-foreground ml-1 font-normal">™</span>
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-[10px] px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-normal">
            <ShieldCheck className="h-3 w-3" />
            <span>Sovereign Personal Vault</span>
          </div>
        </div>

        {/* Title Header */}
        <div className="space-y-1.5">
          <h1 className="text-xl sm:text-2xl font-normal tracking-tight text-foreground flex items-center gap-2">
            <Bot className="h-5 w-5 text-indigo-400" />
            Personal Context Setup
          </h1>
          <p className="text-xs text-muted-foreground leading-relaxed max-w-2xl">
            Contexta conducts a quick adaptive interview to build your sovereign memory foundation. Your answers are categorized into persistent memory nodes in real time.
          </p>
        </div>

        {/* Error message if passed in query */}
        {params.error && (
          <div className="rounded border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400">
            {params.error}
          </div>
        )}

        {/* Interactive Onboarding Chat */}
        <OnboardingChat initialName={initialName} />

        <p className="text-center text-[10px] text-muted-foreground leading-normal">
          You can inspect, search, or update your personal context at any time from the Memory Vault tab or via natural conversation in connected agents.
        </p>
      </div>
    </main>
  );
}

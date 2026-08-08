"use client";

import React from "react";
import { SpotlightCard } from "@/components/ui/spotlight";
import { Button } from "@/components/ui/button";
import { Star, AlertCircle, GitPullRequest, Github } from "lucide-react";

export function Community() {
  const communityCards = [
    {
      title: "Star us on GitHub",
      description: "Support our open-source journey. Star the Contexta repository to help other developers discover self-hosted memory layer frameworks.",
      icon: Star,
      ctaText: "Star on GitHub",
      href: "https://github.com/Aethlon/Contexta",
      primary: true
    },
    {
      title: "Raise an Issue",
      description: "Encountered a bug or need a specific feature? Open a tracking issue on GitHub. We review all community feedback daily.",
      icon: AlertCircle,
      ctaText: "Report an Issue",
      href: "https://github.com/Aethlon/Contexta/issues"
    },
    {
      title: "Contribute Code",
      description: "Align your changes with our pipelines. Read our guidelines to set up Go, Celery, and Postgres testing environments and submit clean PRs.",
      icon: GitPullRequest,
      ctaText: "Read Guidelines",
      href: "https://github.com/Aethlon/Contexta#local-development"
    }
  ];

  return (
    <section className="py-24 border-t border-[var(--color-border)] relative" id="community">
      {/* Subtle Purple Blur BG */}
      <div className="absolute top-[40%] left-[15%] w-[250px] h-[250px] rounded-full bg-[var(--color-purple)]/2 blur-[90px] pointer-events-none z-0" />

      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 relative z-10">
        <div className="text-center max-w-3xl mx-auto mb-18 flex flex-col items-center">
          <div className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--color-charcoal)] border border-[var(--color-border)] text-[var(--color-purple)] mb-4">
            <Github className="h-5 w-5" />
          </div>
          <h2 className="text-3xl font-bold tracking-tight text-[var(--color-foreground)] sm:text-4xl">
            Built in the Open
          </h2>
          <p className="mt-4 text-base text-[var(--color-smoke)] leading-relaxed font-light">
            Contexta is open-source and built for developers. Star the project, report bugs, or submit pull requests to help align agent memory standards.
          </p>
        </div>

        {/* Community Bento Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {communityCards.map((card, idx) => {
            const Icon = card.icon;
            
            return (
              <SpotlightCard
                key={idx}
                className="flex flex-col justify-between min-h-[260px] hover:border-[var(--color-purple)]/40 transition-colors duration-500"
              >
                <div>
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-charcoal)] border border-[var(--color-border)] text-[var(--color-purple)] mb-6">
                    <Icon className="h-5 w-5" />
                  </div>
                  <h3 className="text-lg font-semibold text-[var(--color-foreground)] mb-2">
                    {card.title}
                  </h3>
                  <p className="text-sm text-[var(--color-smoke)] leading-relaxed font-light mb-6">
                    {card.description}
                  </p>
                </div>

                <Button
                  variant={card.primary ? "gold" : "outline"} // Variant "gold" maps to var(--color-purple) in button.tsx
                  className="w-full justify-center"
                  onClick={() => window.open(card.href, "_blank", "noopener,noreferrer")}
                >
                  {card.ctaText}
                </Button>
              </SpotlightCard>
            );
          })}
        </div>
      </div>
    </section>
  );
}

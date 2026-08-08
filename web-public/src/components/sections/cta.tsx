"use client";

import React from "react";
import { motion } from "framer-motion";
import { ArrowRight, Github } from "lucide-react";
import { Button } from "@/components/ui/button";

export function CTA() {
  return (
    <section className="py-24 border-t border-[var(--color-border)] bg-[var(--color-abyss)] relative overflow-hidden" id="cta">
      {/* Glows */}
      <div className="absolute -top-24 -left-24 h-64 w-64 rounded-full bg-[var(--color-purple)]/10 blur-[100px] pointer-events-none" />
      <div className="absolute -bottom-24 -right-24 h-64 w-64 rounded-full bg-[var(--color-purple)]/10 blur-[100px] pointer-events-none" />

      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          className="relative overflow-hidden rounded-3xl border border-[var(--color-purple)]/20 bg-gradient-to-br from-[var(--color-ash)] via-[var(--color-charcoal)] to-[var(--color-abyss)] px-8 py-16 text-center shadow-2xl"
        >
          <h2 className="text-3xl font-bold tracking-tight text-[var(--color-foreground)] sm:text-4xl md:text-5xl mb-4">
            Give your agents a memory they can trust.
          </h2>
          <p className="text-base text-[var(--color-smoke)] mb-10 font-light leading-relaxed max-w-2xl mx-auto">
            Persistent, self-correcting, explainable memory — with your own keys, sub-100ms retrieval, and zero token markups. Start free in minutes.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Button
              variant="gold"
              size="lg"
              className="w-full sm:w-auto group gap-2"
              onClick={() => window.open("https://app.contexta.dev", "_blank", "noopener,noreferrer")}
            >
              <span>Start building free</span>
              <div className="relative w-4 h-4 overflow-hidden flex items-center justify-center">
                <ArrowRight className="h-4 w-4 absolute transition-transform duration-300 group-hover:translate-x-5" />
                <ArrowRight className="h-4 w-4 absolute -translate-x-5 transition-transform duration-300 group-hover:translate-x-0" />
              </div>
            </Button>
            <Button
              variant="outline"
              size="lg"
              className="w-full sm:w-auto gap-2"
              onClick={() => window.open("https://github.com/Aethlon/Contexta", "_blank", "noopener,noreferrer")}
            >
              <Github className="h-4.5 w-4.5 text-[var(--color-purple)]" />
              Self-host it instead
            </Button>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

"use client";

import React, { useState, useEffect } from "react";
import { useTheme } from "@/app/providers";
import { Sun, Moon, Github, Menu, X, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { motion, AnimatePresence } from "framer-motion";

export function Navbar() {
  const { theme, toggleTheme } = useTheme();
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [githubHovered, setGithubHovered] = useState(false);

  useEffect(() => {
    const raf = requestAnimationFrame(() => setMounted(true));
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener("scroll", handleScroll);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", handleScroll);
    };
  }, []);

  const navLinks = [
    { label: "Features", href: "#features" },
    { label: "How it Works", href: "#how-it-works" },
    { label: "Pricing", href: "#pricing" },
    { label: "Dashboard", href: "https://app.contexta.dev", external: true },
    { label: "Docs", href: "https://contexta.dev/docs", external: true },
    { label: "FAQ", href: "#faq" }
  ];

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? "bg-[var(--color-abyss)]/80 backdrop-blur-md border-b border-[var(--color-border)] py-3"
          : "bg-transparent py-5"
      }`}
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between">
          {/* Logo */}
          <a href="#" className="flex items-center gap-2 group">
            <span className="font-mono text-xl font-bold tracking-tight text-[var(--color-foreground)] transition-colors group-hover:text-[var(--color-purple)]">
              Contexta
            </span>
          </a>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-8">
            {navLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                target={link.external ? "_blank" : undefined}
                rel={link.external ? "noopener noreferrer" : undefined}
                className="text-sm font-medium text-[var(--color-smoke)] transition-colors hover:text-[var(--color-foreground)]"
              >
                {link.label}
              </a>
            ))}
          </nav>

          {/* Right side CTAs */}
          <div className="hidden md:flex items-center gap-4">
            {/* Start free */}
            <Button
              variant="gold"
              size="sm"
              onClick={() => window.open("https://app.contexta.dev", "_blank", "noopener,noreferrer")}
            >
              Start free
            </Button>

            {/* Theme Toggle */}
            <button
              onClick={toggleTheme}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--color-border)] bg-transparent text-[var(--color-smoke)] transition-all hover:bg-[var(--color-charcoal)] hover:text-[var(--color-foreground)] overflow-hidden"
              aria-label="Toggle theme"
            >
              {mounted ? (
                <motion.div
                  key={theme}
                  initial={{ rotate: -90, scale: 0.5, opacity: 0 }}
                  animate={{ rotate: 0, scale: 1, opacity: 1 }}
                  whileHover={{ scale: 1.1, rotate: 15 }}
                  whileTap={{ scale: 0.9 }}
                  transition={{ type: "spring", stiffness: 300, damping: 15 }}
                  className="flex items-center justify-center"
                >
                  {theme === "dark" ? (
                    <Sun className="h-4.5 w-4.5 text-amber-500" />
                  ) : (
                    <Moon className="h-4.5 w-4.5 text-indigo-500" />
                  )}
                </motion.div>
              ) : (
                <Sun className="h-4.5 w-4.5" />
              )}
            </button>

            {/* GitHub */}
            <a
              href="https://github.com/Aethlon/Contexta"
              target="_blank"
              rel="noopener noreferrer"
              onMouseEnter={() => setGithubHovered(true)}
              onMouseLeave={() => setGithubHovered(false)}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--color-border)] bg-transparent text-[var(--color-smoke)] transition-all hover:bg-[var(--color-charcoal)] hover:text-[var(--color-foreground)] overflow-hidden"
              aria-label="GitHub Repository"
            >
              <AnimatePresence mode="wait">
                {githubHovered ? (
                  <motion.div
                    key="star"
                    initial={{ scale: 0.6, rotate: -45, opacity: 0 }}
                    animate={{ scale: 1, rotate: 0, opacity: 1 }}
                    exit={{ scale: 0.6, rotate: 45, opacity: 0 }}
                    transition={{ duration: 0.15 }}
                  >
                    <Star className="h-4.5 w-4.5 text-amber-500 fill-amber-500" />
                  </motion.div>
                ) : (
                  <motion.div
                    key="github"
                    initial={{ scale: 0.6, rotate: 45, opacity: 0 }}
                    animate={{ scale: 1, rotate: 0, opacity: 1 }}
                    exit={{ scale: 0.6, rotate: -45, opacity: 0 }}
                    transition={{ duration: 0.15 }}
                  >
                    <Github className="h-4.5 w-4.5" />
                  </motion.div>
                )}
              </AnimatePresence>
            </a>
          </div>

          {/* Mobile menu toggle */}
          <div className="flex md:hidden items-center gap-3">
            <button
              onClick={toggleTheme}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--color-border)] bg-transparent text-[var(--color-smoke)] overflow-hidden"
              aria-label="Toggle theme"
            >
              {mounted ? (
                <motion.div
                  key={theme}
                  initial={{ rotate: -90, scale: 0.5, opacity: 0 }}
                  animate={{ rotate: 0, scale: 1, opacity: 1 }}
                  whileTap={{ scale: 0.9 }}
                  transition={{ type: "spring", stiffness: 300, damping: 15 }}
                  className="flex items-center justify-center"
                >
                  {theme === "dark" ? (
                    <Sun className="h-4.5 w-4.5 text-amber-500" />
                  ) : (
                    <Moon className="h-4.5 w-4.5 text-indigo-500" />
                  )}
                </motion.div>
              ) : (
                <Sun className="h-4.5 w-4.5" />
              )}
            </button>
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--color-border)] text-[var(--color-smoke)]"
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Menu Panel */}
      {mobileMenuOpen && (
        <div className="md:hidden border-b border-[var(--color-border)] bg-[var(--color-abyss)]/95 backdrop-blur-md px-4 py-4 space-y-3 absolute top-full left-0 right-0 z-40">
          {navLinks.map((link) => (
            <a
              key={link.href}
              href={link.href}
              target={link.external ? "_blank" : undefined}
              rel={link.external ? "noopener noreferrer" : undefined}
              onClick={() => setMobileMenuOpen(false)}
              className="block py-2 text-base font-medium text-[var(--color-smoke)] hover:text-[var(--color-foreground)]"
            >
              {link.label}
            </a>
          ))}
          <div className="pt-3 border-t border-[var(--color-border)]">
            <Button
              variant="gold"
              className="w-full"
              onClick={() => {
                setMobileMenuOpen(false);
                window.open("https://app.contexta.dev", "_blank", "noopener,noreferrer");
              }}
            >
              Start free
            </Button>
          </div>
          <div className="flex items-center gap-4 pt-3 border-t border-[var(--color-border)]">
            <a
              href="https://github.com/Aethlon/Contexta"
              target="_blank"
              rel="noopener noreferrer"
              onMouseEnter={() => setGithubHovered(true)}
              onMouseLeave={() => setGithubHovered(false)}
              className="flex items-center gap-2 text-sm text-[var(--color-smoke)] overflow-hidden"
            >
              <div className="h-5 w-5 flex items-center justify-center">
                {githubHovered ? (
                  <Star className="h-5 w-5 text-amber-500 fill-amber-500" />
                ) : (
                  <Github className="h-5 w-5" />
                )}
              </div>
              <span>GitHub</span>
            </a>
          </div>
        </div>
      )}
    </header>
  );
}

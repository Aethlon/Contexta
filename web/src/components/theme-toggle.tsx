"use client";

import { useTheme } from "@/app/providers";
import { Sun, Moon } from "lucide-react";
import { motion } from "framer-motion";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <motion.button
      onClick={toggleTheme}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      className="flex items-center justify-center p-2 rounded-xl text-neutral-500 hover:text-[var(--color-ghost)] transition-colors focus:outline-none"
      aria-label="Toggle Theme"
      type="button"
    >
      {theme === "dark" ? (
        <Sun size={18} strokeWidth={1.2} fill="none" />
      ) : (
        <Moon size={18} strokeWidth={1.2} fill="none" />
      )}
    </motion.button>
  );
}

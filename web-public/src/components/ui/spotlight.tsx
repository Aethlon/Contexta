"use client";

import React, { useState, useEffect } from "react";
import { cn } from "@/lib/utils";

interface SpotlightCardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  glowColor?: string;
  className?: string;
}

export function SpotlightCard({
  children,
  glowColor = "rgba(168, 85, 247, 0.08)", // Brand purple glow
  className,
  ...props
}: SpotlightCardProps) {
  const [coords, setCoords] = useState({ x: 0, y: 0 });
  const [isHovered, setIsHovered] = useState(false);
  const [isMobile, setIsMobile] = useState(true);

  // Disable custom cursor tracking on mobile/touch screens to avoid CPU overhead
  useEffect(() => {
    const checkFinePointer = window.matchMedia("(pointer: fine)");
    const raf = requestAnimationFrame(() => setIsMobile(!checkFinePointer.matches));

    const handler = (e: MediaQueryListEvent) => {
      setIsMobile(!e.matches);
    };
    checkFinePointer.addEventListener("change", handler);
    return () => {
      cancelAnimationFrame(raf);
      checkFinePointer.removeEventListener("change", handler);
    };
  }, []);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (isMobile) return;
    const rect = e.currentTarget.getBoundingClientRect();
    setCoords({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
  };

  return (
    <div
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={cn(
        "relative overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-ash)] p-6 transition-all duration-300",
        className
      )}
      {...props}
    >
      {/* Glow layer */}
      {isHovered && !isMobile && (
        <div
          className="pointer-events-none absolute -inset-px transition-opacity duration-300 z-0"
          style={{
            background: `radial-gradient(280px circle at ${coords.x}px ${coords.y}px, ${glowColor}, transparent 80%)`,
          }}
        />
      )}
      <div className="relative z-10">{children}</div>
    </div>
  );
}

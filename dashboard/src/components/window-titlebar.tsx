"use client";

import React, { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Minus, Square, Copy, X, ChevronLeft, ChevronRight, RotateCw, Shield, Sparkles } from "lucide-react";
import { ContextaMark } from "@/components/contexta-logo";

export function WindowTitlebar() {
  const router = useRouter();
  const pathname = usePathname();
  const [isTauri, setIsTauri] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);

  useEffect(() => {
    // Check if running within Tauri desktop environment
    if (typeof window !== "undefined" && ("__TAURI_INTERNALS__" in window || "__TAURI__" in window)) {
      setIsTauri(true);
    }
  }, []);

  const handleMinimize = async () => {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("minimize_window");
    } catch {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        await getCurrentWindow().minimize();
      } catch (err) {
        console.warn("Minimize not available outside Tauri:", err);
      }
    }
  };

  const handleToggleMaximize = async () => {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("toggle_maximize_window");
      setIsMaximized((prev) => !prev);
    } catch {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        await getCurrentWindow().toggleMaximize();
        setIsMaximized((prev) => !prev);
      } catch (err) {
        console.warn("Maximize not available outside Tauri:", err);
      }
    }
  };

  const handleClose = async () => {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("close_window");
    } catch {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        await getCurrentWindow().close();
      } catch (err) {
        console.warn("Close not available outside Tauri:", err);
      }
    }
  };

  return (
    <div
      data-tauri-drag-region
      className="h-9 w-full bg-background/95 border-b border-border/40 select-none flex items-center justify-between px-3 text-xs font-mono text-muted-foreground z-50 sticky top-0 backdrop-blur-md"
    >
      {/* Left: Custom Navigation & App Title */}
      <div className="flex items-center gap-3" data-tauri-drag-region>
        <div className="flex items-center gap-1.5" data-tauri-drag-region>
          <ContextaMark className="size-3.5 text-foreground" />
          <span className="font-medium text-foreground tracking-tight text-[11px]">contexta</span>
          <span className="text-[9px] px-1 py-0.2 rounded bg-foreground/10 text-muted-foreground font-mono">
            desktop
          </span>
        </div>

        {/* Custom History Navigation Controls */}
        <div className="flex items-center gap-0.5 ml-2 border-l border-border/40 pl-2.5">
          <button
            type="button"
            onClick={() => router.back()}
            title="Go back"
            className="p-1 rounded hover:bg-secondary/60 hover:text-foreground transition-colors cursor-pointer"
          >
            <ChevronLeft className="size-3.5" />
          </button>
          <button
            type="button"
            onClick={() => router.forward()}
            title="Go forward"
            className="p-1 rounded hover:bg-secondary/60 hover:text-foreground transition-colors cursor-pointer"
          >
            <ChevronRight className="size-3.5" />
          </button>
          <button
            type="button"
            onClick={() => router.refresh()}
            title="Reload views"
            className="p-1 rounded hover:bg-secondary/60 hover:text-foreground transition-colors cursor-pointer"
          >
            <RotateCw className="size-3" />
          </button>
        </div>
      </div>

      {/* Center: Draggable Title / Breadcrumb */}
      <div
        data-tauri-drag-region
        className="flex-1 h-full flex items-center justify-center text-[11px] text-muted-foreground/80 tracking-wide font-mono pointer-events-none truncate px-4"
      >
        <span>Contexta Sovereign Memory Console</span>
      </div>

      {/* Right: Custom Windows Controls */}
      <div className="flex items-center h-full">
        {/* Minimize Button */}
        <button
          type="button"
          onClick={handleMinimize}
          title="Minimize"
          className="h-full px-3 flex items-center justify-center hover:bg-secondary/70 text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
        >
          <Minus className="size-3.5" />
        </button>

        {/* Maximize / Restore Button */}
        <button
          type="button"
          onClick={handleToggleMaximize}
          title={isMaximized ? "Restore" : "Maximize"}
          className="h-full px-3 flex items-center justify-center hover:bg-secondary/70 text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
        >
          {isMaximized ? <Copy className="size-3" /> : <Square className="size-3" />}
        </button>

        {/* Close Button */}
        <button
          type="button"
          onClick={handleClose}
          title="Close"
          className="h-full px-3.5 flex items-center justify-center hover:bg-red-500 hover:text-white text-muted-foreground transition-colors cursor-pointer"
        >
          <X className="size-3.5" />
        </button>
      </div>
    </div>
  );
}

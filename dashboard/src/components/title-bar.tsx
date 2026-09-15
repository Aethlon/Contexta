"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Minus, Square, Copy, X, ChevronLeft, ChevronRight, RotateCw, ShieldCheck } from "lucide-react";
import { ContextaMark } from "@/components/contexta-logo";

export function TitleBar() {
  const router = useRouter();
  const [isTauri, setIsTauri] = useState(true); // Default show custom controls
  const [isMaximized, setIsMaximized] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const hasTauri = "__TAURI_INTERNALS__" in window || "__TAURI__" in window;
      setIsTauri(hasTauri || process.env.NODE_ENV === "development");
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
        console.warn("Minimize window:", err);
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
        console.warn("Maximize window:", err);
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
        console.warn("Close window:", err);
      }
    }
  };

  return (
    <div
      data-tauri-drag-region
      className="sticky top-0 z-50 flex h-9 w-full select-none items-center justify-between border-b border-border/40 bg-background/95 backdrop-blur-md px-3 font-mono text-[11px]"
    >
      {/* Left: Window Brand & Custom History Navigation */}
      <div data-tauri-drag-region className="flex items-center gap-2 text-foreground/90 cursor-default">
        <span className="flex size-4.5 items-center justify-center rounded border border-border/40 bg-secondary/70 text-foreground">
          <ContextaMark className="size-3" />
        </span>
        <span data-tauri-drag-region className="font-medium tracking-tight text-foreground">
          Contexta
        </span>
        <span className="text-muted-foreground/60">—</span>
        <span data-tauri-drag-region className="text-muted-foreground hidden sm:inline">
          Sovereign Memory Console
        </span>

        {/* Custom Navigation Controls (Back, Forward, Reload) */}
        <div className="flex items-center gap-0.5 ml-3 border-l border-border/40 pl-2">
          <button
            type="button"
            onClick={() => router.back()}
            title="Go back"
            className="p-1 rounded hover:bg-secondary/70 hover:text-foreground text-muted-foreground transition-colors cursor-pointer"
          >
            <ChevronLeft className="size-3.5" />
          </button>
          <button
            type="button"
            onClick={() => router.forward()}
            title="Go forward"
            className="p-1 rounded hover:bg-secondary/70 hover:text-foreground text-muted-foreground transition-colors cursor-pointer"
          >
            <ChevronRight className="size-3.5" />
          </button>
          <button
            type="button"
            onClick={() => router.refresh()}
            title="Reload current page"
            className="p-1 rounded hover:bg-secondary/70 hover:text-foreground text-muted-foreground transition-colors cursor-pointer"
          >
            <RotateCw className="size-3" />
          </button>
        </div>
      </div>

      {/* Center: Draggable Spacer with Secure Offline Badge */}
      <div data-tauri-drag-region className="flex-1 flex justify-center items-center h-full cursor-default">
        <div data-tauri-drag-region className="hidden md:flex items-center gap-1.5 text-[10px] text-muted-foreground/70">
          <ShieldCheck className="h-3 w-3 text-emerald-400/80" />
          <span>Offline-First Enclave</span>
        </div>
      </div>

      {/* Right: Custom Windows Controls */}
      <div className="flex items-center">
        <button
          type="button"
          onClick={handleMinimize}
          title="Minimize"
          className="flex h-9 w-10 items-center justify-center text-muted-foreground hover:bg-secondary/60 hover:text-foreground transition-colors cursor-pointer"
        >
          <Minus className="h-3 w-3" />
        </button>
        <button
          type="button"
          onClick={handleToggleMaximize}
          title={isMaximized ? "Restore" : "Maximize"}
          className="flex h-9 w-10 items-center justify-center text-muted-foreground hover:bg-secondary/60 hover:text-foreground transition-colors cursor-pointer"
        >
          {isMaximized ? <Copy className="h-2.5 w-2.5" /> : <Square className="h-2.5 w-2.5" />}
        </button>
        <button
          type="button"
          onClick={handleClose}
          title="Close"
          className="flex h-9 w-10 items-center justify-center text-muted-foreground hover:bg-red-500 hover:text-white transition-colors cursor-pointer"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

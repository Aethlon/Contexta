"use client";

import { useEffect, useRef, useState } from "react";
import { ZoomIn, ZoomOut, Maximize2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/app/providers";

type Node = { id: string; name: string; entity_type: string; memory_count: number };
type Edge = { source: string; target: string; relationship_type: string };

export function EntityGraphView({ nodes, edges }: { nodes: Node[]; edges: Edge[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [scale, setScale] = useState(1);
  const animRef = useRef<number>(0);
  const [visible, setVisible] = useState(false);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const { theme } = useTheme();

  useEffect(() => {
    const el = containerRef.current;
    if (!el || nodes.length === 0) return;
    observerRef.current = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) setVisible(true); },
      { threshold: 0.1 }
    );
    observerRef.current.observe(el);
    return () => observerRef.current?.disconnect();
  }, [nodes.length]);

  useEffect(() => {
    if (!visible || nodes.length === 0) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;
    const centerX = w / 2;
    const centerY = h / 2;

    const colors: Record<string, string> = {
      person: "#3b82f6",
      topic: "#10b981",
      preference: "#f59e0b",
      organization: "#8b5cf6",
      location: "#ef4444",
    };

    const positions: Map<string, { x: number; y: number; vx: number; vy: number }> = new Map();
    const nodeMap = new Map<string, Node>();
    for (const n of nodes) nodeMap.set(n.id, n);

    const maxRadius = 30;
    const minRadius = 12;
    const maxCount = Math.max(...nodes.map((n) => n.memory_count || 1), 1);
    for (const n of nodes) {
      const angle = Math.random() * Math.PI * 2;
      const dist = Math.random() * Math.min(w, h) * 0.3;
      positions.set(n.id, { x: centerX + Math.cos(angle) * dist, y: centerY + Math.sin(angle) * dist, vx: 0, vy: 0 });
    }

    let running = true;
    const tick = () => {
      if (!running) return;
      ctx.clearRect(0, 0, w, h);

      ctx.save();
      ctx.translate(centerX, centerY);
      ctx.scale(scale, scale);
      ctx.translate(-centerX, -centerY);

      // repulsion
      const entries = [...positions.entries()];
      for (let i = 0; i < entries.length; i++) {
        for (let j = i + 1; j < entries.length; j++) {
          const a = entries[i][1];
          const b = entries[j][1];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 800 / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a.vx += fx; a.vy += fy;
          b.vx -= fx; b.vy -= fy;
        }
      }

      // attraction + centering
      for (const [, pos] of entries) {
        pos.vx += (centerX - pos.x) * 0.005;
        pos.vy += (centerY - pos.y) * 0.005;
      }

      // attract connected nodes
      for (const e of edges) {
        const a = positions.get(e.source);
        const b = positions.get(e.target);
        if (a && b) {
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = dist * 0.001;
          a.vx += dx * force;
          a.vy += dy * force;
          b.vx -= dx * force;
          b.vy -= dy * force;
        }
      }

      // integrate
      for (const pos of positions.values()) {
        pos.vx *= 0.5;
        pos.vy *= 0.5;
        pos.x += pos.vx;
        pos.y += pos.vy;
      }

      // edges
      ctx.strokeStyle = theme === "dark" ? "rgba(148, 163, 184, 0.15)" : "rgba(100, 116, 139, 0.15)";
      ctx.lineWidth = 1;
      for (const e of edges) {
        const a = positions.get(e.source);
        const b = positions.get(e.target);
        if (a && b) {
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }

      // nodes
      ctx.font = "10px system-ui";
      ctx.textAlign = "center";
      for (const [id, pos] of positions) {
        const node = nodeMap.get(id);
        if (!node) continue;
        const r = minRadius + ((node.memory_count || 1) / maxCount) * (maxRadius - minRadius);
        const color = colors[node.entity_type] || "#6b7280";

        ctx.beginPath();
        ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2);
        ctx.fillStyle = `${color}15`;
        ctx.fill();
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.2;
        ctx.stroke();

        ctx.fillStyle = theme === "dark" ? "#f8fafc" : "#09090B";
        const name = node.name.length > 14 ? node.name.slice(0, 12) + "…" : node.name;
        ctx.fillText(name, pos.x, pos.y + 3);
        ctx.fillStyle = color;
        ctx.fillText(`×${node.memory_count || 1}`, pos.x, pos.y - r - 5);
      }

      ctx.restore();
      animRef.current = requestAnimationFrame(tick);
    };

    tick();
    return () => { running = false; cancelAnimationFrame(animRef.current); };
  }, [visible, nodes, edges, scale, theme]);

  if (nodes.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] text-sm text-[var(--color-smoke)] font-light">
        No entities extracted yet
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="mb-3 flex gap-2">
        <Button variant="outline" onClick={() => setScale((s) => Math.max(0.3, s - 0.1))} className="h-8 w-8 p-0">
          <ZoomOut className="h-3.5 w-3.5" strokeWidth={1.2} />
        </Button>
        <Button variant="outline" onClick={() => setScale((s) => Math.min(3, s + 0.1))} className="h-8 w-8 p-0">
          <ZoomIn className="h-3.5 w-3.5" strokeWidth={1.2} />
        </Button>
        <Button variant="outline" onClick={() => setScale(1)} className="h-8 w-8 p-0">
          <Maximize2 className="h-3.5 w-3.5" strokeWidth={1.2} />
        </Button>
      </div>
      <canvas ref={canvasRef} className="h-72 w-full rounded-2xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)]" />
      <div className="mt-3 flex flex-wrap gap-3 text-xs text-[var(--color-smoke)]">
        {["person", "topic", "preference", "organization", "location"].map((type) => (
          <span key={type} className="flex items-center gap-1.5 font-light">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: ({ person: "#3b82f6", topic: "#10b981", preference: "#f59e0b", organization: "#8b5cf6", location: "#ef4444" } as any)[type] }} />
            {type}
          </span>
        ))}
      </div>
    </div>
  );
}

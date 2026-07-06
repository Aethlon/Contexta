"use client";

import { useEffect, useRef, useState } from "react";
import type { GraphNode, GraphEdge } from "@/lib/contexta-api";

type Position = { x: number; y: number; vx: number; vy: number };

const COLORS: Record<string, string> = {
  person: "#3b82f6",
  organization: "#8b5cf6",
  concept: "#10b981",
  technology: "#f59e0b",
  location: "#ef4444",
  product: "#ec4899",
  default: "#6b7280",
};

function nodeColor(type: string): string {
  return COLORS[type] ?? COLORS.default;
}

export function EntityGraph({
  nodes: initialNodes,
  edges: initialEdges,
  width = 700,
  height = 450,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  width?: number;
  height?: number;
}) {
  const [positions, setPositions] = useState<Map<string, Position>>(new Map());
  const frameRef = useRef<number>(0);

  useEffect(() => {
    if (initialNodes.length === 0) return;

    const pos = new Map<string, Position>();
    for (const n of initialNodes) {
      pos.set(n.id, {
        x: Math.random() * width,
        y: Math.random() * height,
        vx: 0,
        vy: 0,
      });
    }

    const nodeIds = new Set(initialNodes.map((n) => n.id));
    const adj = new Map<string, Set<string>>();
    for (const n of initialNodes) {
      adj.set(n.id, new Set());
    }
    for (const e of initialEdges) {
      if (nodeIds.has(e.source) && nodeIds.has(e.target)) {
        adj.get(e.source)?.add(e.target);
        adj.get(e.target)?.add(e.source);
      }
    }

    let running = true;
    const tick = () => {
      if (!running) return;
      let moved = 0;

      for (const n of initialNodes) {
        const p = pos.get(n.id)!;
        let fx = 0;
        let fy = 0;

        // center gravity
        fx += (width / 2 - p.x) * 0.001;
        fy += (height / 2 - p.y) * 0.001;

        // repulsion
        for (const n2 of initialNodes) {
          if (n2.id === n.id) continue;
          const p2 = pos.get(n2.id)!;
          let dx = p.x - p2.x;
          let dy = p.y - p2.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 600 / (dist * dist);
          dx = (dx / dist) * force;
          dy = (dy / dist) * force;
          fx += dx;
          fy += dy;
        }

        // attraction along edges
        for (const neighborId of adj.get(n.id) ?? []) {
          const p2 = pos.get(neighborId);
          if (!p2) continue;
          const dx = p2.x - p.x;
          const dy = p2.y - p.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = dist * 0.005;
          fx += (dx / dist) * force;
          fy += (dy / dist) * force;
        }

        p.vx = (p.vx + fx) * 0.85;
        p.vy = (p.vy + fy) * 0.85;
        p.x += p.vx;
        p.y += p.vy;

        // clamp
        p.x = Math.max(10, Math.min(width - 10, p.x));
        p.y = Math.max(10, Math.min(height - 10, p.y));

        moved += Math.abs(p.vx) + Math.abs(p.vy);
      }

      setPositions(new Map(pos));

      if (moved > 0.1) {
        frameRef.current = requestAnimationFrame(tick);
      }
    };

    frameRef.current = requestAnimationFrame(tick);

    return () => {
      running = false;
      cancelAnimationFrame(frameRef.current);
    };
  }, [initialNodes, initialEdges, width, height]);

  if (initialNodes.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-border bg-background text-sm text-muted-foreground">
        No entities yet. Store observations to build the graph.
      </div>
    );
  }

  const nodeById = new Map(initialNodes.map((n) => [n.id, n]));

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-full w-full">
      {/* Edges */}
      {initialEdges.map((edge, i) => {
        const sp = positions.get(edge.source);
        const tp = positions.get(edge.target);
        if (!sp || !tp) return null;
        return (
          <line
            key={`edge-${i}`}
            x1={sp.x}
            y1={sp.y}
            x2={tp.x}
            y2={tp.y}
            stroke="#374151"
            strokeWidth={1}
          />
        );
      })}
      {/* Nodes */}
      {initialNodes.map((node) => {
        const p = positions.get(node.id);
        if (!p) return null;
        const color = nodeColor(node.entity_type);
        const r = Math.min(8 + node.memory_count * 2, 20);
        return (
          <g key={node.id}>
            <circle cx={p.x} cy={p.y} r={r} fill={color} opacity={0.8} />
            <title>{node.name} ({node.entity_type})</title>
            <text
              x={p.x}
              y={p.y + r + 12}
              textAnchor="middle"
              fill="#d1d5db"
              fontSize={10}
            >
              {node.name.length > 16 ? node.name.slice(0, 14) + "…" : node.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

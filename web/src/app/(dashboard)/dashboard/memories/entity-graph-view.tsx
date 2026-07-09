"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import { Maximize2, Minimize2, X, Table2, Share2 } from "lucide-react";
import { Button } from "@/components/ui/button";

type Node = { id: string; name: string; entity_type: string; memory_count: number; summary?: string | null };
type Edge = { source: string; target: string; relationship_type: string };

const COLORS: Record<string, string> = {
  person: "#3b82f6",
  topic: "#10b981",
  preference: "#f59e0b",
  organization: "#8b5cf6",
  location: "#ef4444",
};
const COLOR_LIST = Object.entries(COLORS);

const BASE_W = 700;
const BASE_H = 400;

function genPositions(nodes: Node[], seed = 0): Map<string, { x: number; y: number }> {
  const map = new Map<string, { x: number; y: number }>();
  const cx = BASE_W / 2;
  const cy = BASE_H / 2;
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    const a = ((i * 137.5 + seed * 73) % 360) * (Math.PI / 180);
    const d = 60 + ((i * 31) % 120);
    map.set(n.id, { x: cx + Math.cos(a) * d, y: cy + Math.sin(a) * d });
  }
  return map;
}

// ---------- Graph SVG ----------
function GraphSVG({
  nodes, edges, positions, hovered, setHovered, selected, setSelected,
  viewBox, onDoubleClick,
}: {
  nodes: Node[]; edges: Edge[]; positions: Map<string, { x: number; y: number }>;
  hovered: string | null; setHovered: (v: string | null) => void;
  selected: Node | null; setSelected: (v: Node | null) => void;
  viewBox: string; onDoubleClick: () => void;
}) {
  const nodeMap = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const maxMem = Math.max(...nodes.map((n) => n.memory_count || 1), 1);

  return (
    <svg viewBox={viewBox} className="w-full h-full rounded-2xl bg-[var(--color-abyss)]" onDoubleClick={onDoubleClick}
      style={{ minHeight: 360 }}
    >
      {/* Edges */}
      {edges.map((e, i) => {
        const a = positions.get(e.source);
        const b = positions.get(e.target);
        if (!a || !b) return null;
        return (
          <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
            stroke="rgba(255,255,255,0.08)" strokeWidth={1} />
        );
      })}

      {/* Nodes */}
      {nodes.map((n) => {
        const p = positions.get(n.id);
        if (!p) return null;
        const color = COLORS[n.entity_type] || "#6b7280";
        const r = 10 + ((n.memory_count || 1) / maxMem) * 20;
        const hl = hovered === n.id || selected?.id === n.id;

        return (
          <g key={n.id}
            onMouseEnter={() => setHovered(n.id)}
            onMouseLeave={() => setHovered(null)}
            onClick={() => setSelected(selected?.id === n.id ? null : n)}
            style={{ cursor: "pointer" }}
          >
            {hl && <circle cx={p.x} cy={p.y} r={r + 6} fill="rgba(255,255,255,0.06)" />}
            <circle cx={p.x} cy={p.y} r={r} fill={color}
              stroke={hl ? "#ffffff" : "rgba(255,255,255,0.25)"}
              strokeWidth={hl ? 2.5 : 1.5} />
            <text x={p.x} y={p.y - r - 6} textAnchor="middle" fill="rgba(255,255,255,0.6)"
              fontSize={9} fontWeight="bold">
              {n.memory_count || 1}
            </text>
            <text x={p.x} y={p.y + 4} textAnchor="middle" fill="#ffffff" fontSize={10}>
              {n.name.length > 14 ? n.name.slice(0, 12) + "\u2026" : n.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ---------- Entity Table ----------
function EntityTable({ nodes, selected, setSelected }: {
  nodes: Node[]; selected: Node | null; setSelected: (v: Node | null) => void;
}) {
  return (
    <div className="w-full rounded-2xl border border-[var(--color-graphite)]/30 bg-[var(--color-abyss)] overflow-hidden"
      style={{ minHeight: 360 }}>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--color-graphite)]/20 text-left">
            <th className="p-3 text-[10px] font-mono tracking-widest text-[var(--color-smoke)] uppercase font-light">Name</th>
            <th className="p-3 text-[10px] font-mono tracking-widest text-[var(--color-smoke)] uppercase font-light">Type</th>
            <th className="p-3 text-[10px] font-mono tracking-widest text-[var(--color-smoke)] uppercase font-light">Memories</th>
            <th className="p-3 text-[10px] font-mono tracking-widest text-[var(--color-smoke)] uppercase font-light">Summary</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--color-graphite)]/10">
          {nodes.map((n) => {
            const isSelected = selected?.id === n.id;
            return (
              <tr key={n.id}
                onClick={() => setSelected(isSelected ? null : n)}
                className={`cursor-pointer transition-colors ${isSelected ? "bg-[var(--color-charcoal)]/40" : "hover:bg-[var(--color-charcoal)]/20"}`}
              >
                <td className="p-3">
                  <div className="flex items-center gap-2">
                    <span className="inline-block h-2 w-2 rounded-full shrink-0" style={{ background: COLORS[n.entity_type] || "#6b7280" }} />
                    <span className="text-[var(--color-ghost)] font-normal">{n.name}</span>
                  </div>
                </td>
                <td className="p-3">
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-[var(--color-graphite)]/20 text-[var(--color-smoke)]">
                    {n.entity_type}
                  </span>
                </td>
                <td className="p-3 font-mono text-xs text-[var(--color-smoke)] tabular-nums">{n.memory_count}</td>
                <td className="p-3 text-xs text-[var(--color-smoke)] font-light max-w-[200px] truncate">{n.summary || "\u2014"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------- Main Component ----------
export function EntityGraphView({ nodes, edges }: { nodes: Node[]; edges: Edge[] }) {
  const [selected, setSelected] = useState<Node | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [view, setView] = useState<"graph" | "table">("graph");
  const [expanded, setExpanded] = useState(false);
  const [zoom, setZoom] = useState(1);

  // Hydration-safe deterministic positions
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }> | null>(null);
  useEffect(() => {
    setPositions(genPositions(nodes, 42));
  }, [nodes]);

  const viewBox = `${(1 - 1 / zoom) * BASE_W / 2} ${(1 - 1 / zoom) * BASE_H / 2} ${BASE_W / zoom} ${BASE_H / zoom}`;

  const handleZoomIn = () => setZoom((z) => Math.min(3, z + 0.3));
  const handleZoomOut = () => setZoom((z) => Math.max(0.4, z - 0.3));
  const handleReset = () => setZoom(1);

  // Shared detail panel
  const detailPanel = selected && (
    <div className="rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1.5 min-w-0">
          <div className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-2.5 rounded-full shrink-0" style={{ background: COLORS[selected.entity_type] || "#6b7280" }} />
            <h4 className="text-sm font-medium text-[var(--color-ghost)] truncate">{selected.name}</h4>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-[var(--color-graphite)]/30 text-[var(--color-smoke)]">{selected.entity_type}</span>
          </div>
          {selected.summary && (
            <p className="text-xs font-light text-[var(--color-smoke)] leading-relaxed">{selected.summary}</p>
          )}
          <p className="text-[10px] font-mono text-[var(--color-smoke)]">
            {selected.memory_count} linked {selected.memory_count === 1 ? "memory" : "memories"}
          </p>
        </div>
        <button onClick={() => setSelected(null)} className="p-1 rounded-md hover:bg-[var(--color-charcoal)] transition-colors">
          <X className="h-3.5 w-3.5 text-[var(--color-smoke)]" strokeWidth={1.2} />
        </button>
      </div>
    </div>
  );

  if (!nodes.length) {
    return (
      <div className="flex h-48 items-center justify-center rounded-xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] text-sm text-[var(--color-smoke)] font-light">
        No entities extracted yet
      </div>
    );
  }

  const content = (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        {/* View toggle */}
        <div className="flex rounded-lg border border-[var(--color-graphite)]/30 overflow-hidden">
          <button onClick={() => setView("graph")}
            className={`px-3 py-1.5 text-xs font-mono transition-colors ${view === "graph" ? "bg-[var(--color-ghost)] text-[var(--color-abyss)]" : "bg-transparent text-[var(--color-smoke)] hover:text-[var(--color-ghost)]"}`}>
            Graph
          </button>
          <button onClick={() => setView("table")}
            className={`px-3 py-1.5 text-xs font-mono transition-colors ${view === "table" ? "bg-[var(--color-ghost)] text-[var(--color-abyss)]" : "bg-transparent text-[var(--color-smoke)] hover:text-[var(--color-ghost)]"}`}>
            Table
          </button>
        </div>

        {/* Graph-only controls */}
        {view === "graph" && (
          <>
            <button onClick={handleZoomOut} className="h-7 w-7 flex items-center justify-center rounded-md border border-[var(--color-graphite)]/30 text-[var(--color-smoke)] hover:text-[var(--color-ghost)] transition-colors text-sm">−</button>
            <button onClick={handleZoomIn} className="h-7 w-7 flex items-center justify-center rounded-md border border-[var(--color-graphite)]/30 text-[var(--color-smoke)] hover:text-[var(--color-ghost)] transition-colors text-sm">+</button>
            <button onClick={handleReset} className="h-7 px-2 flex items-center justify-center rounded-md border border-[var(--color-graphite)]/30 text-[var(--color-smoke)] hover:text-[var(--color-ghost)] transition-colors text-[10px] font-mono">Reset</button>
          </>
        )}

        <span className="ml-auto text-[10px] font-mono text-[var(--color-smoke)]">
          {nodes.length} {nodes.length === 1 ? "entity" : "entities"}
        </span>

        {/* Expand */}
        <button onClick={() => setExpanded(!expanded)}
          className="h-7 w-7 flex items-center justify-center rounded-md border border-[var(--color-graphite)]/30 text-[var(--color-smoke)] hover:text-[var(--color-ghost)] transition-colors">
          {expanded ? <Minimize2 className="h-3.5 w-3.5" strokeWidth={1.2} /> : <Maximize2 className="h-3.5 w-3.5" strokeWidth={1.2} />}
        </button>
      </div>

      {/* Content */}
      {view === "graph" ? (
        positions ? (
          <GraphSVG nodes={nodes} edges={edges} positions={positions}
            hovered={hovered} setHovered={setHovered}
            selected={selected} setSelected={setSelected}
            viewBox={viewBox} onDoubleClick={handleReset} />
        ) : (
          <div className="flex items-center justify-center h-[360px] rounded-2xl border border-[var(--color-graphite)]/30 bg-[var(--color-abyss)] text-sm text-[var(--color-smoke)] font-light">
            Loading graph…
          </div>
        )
      ) : (
        positions && <EntityTable nodes={nodes} selected={selected} setSelected={setSelected} />
      )}

      {/* Legend (graph only) */}
      {view === "graph" && (
        <div className="flex flex-wrap gap-3 text-xs text-[var(--color-smoke)]">
          {COLOR_LIST.map(([type, color]) => (
            <span key={type} className="flex items-center gap-1.5 font-light">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />
              {type}
            </span>
          ))}
        </div>
      )}

      {/* Detail panel */}
      {detailPanel}
    </div>
  );

  // Expanded overlay
  if (expanded) {
    return (
      <>
        {/* Inline content */}
        {content}
        {/* Overlay */}
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-6"
          onClick={() => setExpanded(false)}>
          <div className="w-full max-w-5xl max-h-[90vh] overflow-auto rounded-2xl border border-[var(--color-graphite)]/30 bg-[var(--color-ash)] p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            {content}
          </div>
        </div>
      </>
    );
  }

  return content;
}

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Maximize2, Minimize2, Search, X } from "lucide-react";

type Node = {
  id: string;
  name: string;
  entity_type: string;
  memory_count: number;
  summary?: string | null;
};
type Edge = { source: string; target: string; relationship_type: string };

/* ---------------------------------------------------------------------------
   Palette
   Semantic, token-driven accents rather than the previous hardcoded hex set, so
   the graph reads correctly in both themes.
--------------------------------------------------------------------------- */
const TYPE_COLOR: Record<string, string> = {
  person: "var(--accent-blue)",
  topic: "var(--accent-green)",
  preference: "var(--accent-yellow)",
  organization: "var(--accent-purple)",
  location: "var(--destructive)",
};
const FALLBACK_COLOR = "var(--text-tertiary)";

const W = 900;
const H = 520;

/* ---------------------------------------------------------------------------
   Layout: a small deterministic force simulation.

   The previous layout dropped every node on a fixed-radius spiral
   (`d = 60 + (i*31)%120`), so 40 entities occupied the same 120px disc and
   overlapped almost completely. This seeds on a ring sized to the node count
   and then relaxes with repulsion + spring + centring, which spreads a graph
   out and keeps connected nodes near each other.
--------------------------------------------------------------------------- */
type Pt = { x: number; y: number; vx: number; vy: number; fx: number; fy: number };

/** Above this the O(n^2) repulsion is both slow and visually busy, so we use the ring. */
const FORCE_LIMIT = 120;
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

function layout(nodes: Node[], edges: Edge[], iterations = 300): Map<string, Pt> {
  const n = nodes.length;
  const pts = new Map<string, Pt>();
  if (n === 0) return pts;

  const degree = new Map<string, number>();
  for (const e of edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }

  // Deterministic ring layout. Used for very dense graphs, where it is both
  // instant and guaranteed to have no coincident nodes.
  if (n > FORCE_LIMIT) {
    const cx = W / 2;
    const cy = H / 2;
    const rings = Math.max(1, Math.ceil(Math.sqrt(n / 6)));
    let idx = 0;
    for (let ri = 0; ri < rings && idx < n; ri++) {
      const per =
        ri === 0 ? 1 : Math.min(n - idx, Math.round((2 * Math.PI * (60 + ri * 95)) / 26));
      for (let i = 0; i < per && idx < n; i++, idx++) {
        const a = (i / per) * Math.PI * 2 + ri * 0.4;
        const r = 60 + ri * 95;
        const node = nodes[idx];
        pts.set(node.id, { x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r * 0.78, vx: 0, vy: 0, fx: 0, fy: 0 });
      }
    }
    return pts;
  }

  const k = Math.sqrt((W * H) / n) * 0.6;
  const MAX_V = 24;
  const MAX_F = k * 3;

  // Seed on a golden-angle ring sized by degree, so well-connected nodes start
  // near the middle. Golden angle rather than Math.random keeps the server and
  // client renders identical.
  nodes.forEach((node, i) => {
    const deg = Math.min(degree.get(node.id) ?? 0, 6);
    const r = (Math.min(W, H) / 2 - 60) * (0.35 + 0.65 * (1 - deg / 6));
    const a = i * 2.399963;
    pts.set(node.id, {
      x: W / 2 + Math.cos(a) * r,
      y: H / 2 + Math.sin(a) * r * 0.72,
      vx: 0,
      vy: 0,
      fx: 0,
      fy: 0,
    });
  });

  const links = edges
    .map((e) => [e.source, e.target] as const)
    .filter(([s, t]) => pts.has(s) && pts.has(t));
  const ids = nodes.map((x) => x.id);

  for (let step = 0; step < iterations; step++) {
    const alpha = 1 - step / iterations;
    for (const p of pts.values()) {
      p.fx = 0;
      p.fy = 0;
    }

    // Repulsion, clamped. Without the clamp the force diverges as k shrinks
    // with node count and positions go to NaN.
    for (let i = 0; i < n; i++) {
      const a = pts.get(ids[i])!;
      for (let j = i + 1; j < n; j++) {
        const b = pts.get(ids[j])!;
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 0.01) {
          dx = ((i % 7) - 3) * 0.5 + 0.5;
          dy = ((j % 7) - 3) * 0.5 + 0.5;
          d2 = dx * dx + dy * dy;
        }
        const d = Math.sqrt(d2);
        const f = Math.min((k * k) / d, MAX_F);
        const ux = dx / d;
        const uy = dy / d;
        a.fx += ux * f;
        a.fy += uy * f;
        b.fx -= ux * f;
        b.fy -= uy * f;
      }
    }

    // Springs pull toward the ideal edge length rather than using d^2/k, which
    // was the other half of the divergence.
    for (const [s, t] of links) {
      const a = pts.get(s)!;
      const b = pts.get(t)!;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d = Math.max(Math.hypot(dx, dy), 0.01);
      const f = clamp((d - k) * 0.5, -MAX_F, MAX_F);
      const ux = dx / d;
      const uy = dy / d;
      a.fx += ux * f;
      a.fy += uy * f;
      b.fx -= ux * f;
      b.fy -= uy * f;
    }

    for (const p of pts.values()) {
      p.vx = (p.vx + p.fx * 0.5 + (W / 2 - p.x) * 0.02) * 0.85;
      p.vy = (p.vy + p.fy * 0.5 + (H / 2 - p.y) * 0.02) * 0.85;
      const v = Math.hypot(p.vx, p.vy);
      if (v > MAX_V) {
        p.vx = (p.vx / v) * MAX_V;
        p.vy = (p.vy / v) * MAX_V;
      }
      p.x = clamp(p.x + p.vx * alpha * 0.5, 40, W - 40);
      p.y = clamp(p.y + p.vy * alpha * 0.5, 30, H - 30);
    }
  }

  // De-overlap pass. The boundary clamp can still leave two nodes sharing a
  // position, which renders as one dot; separate anything closer than a label
  // can fit.
  const minSep = 34;
  for (let pass = 0; pass < 24; pass++) {
    let moved = false;
    for (let i = 0; i < n; i++) {
      const a = pts.get(ids[i])!;
      for (let j = i + 1; j < n; j++) {
        const b = pts.get(ids[j])!;
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let d = Math.hypot(dx, dy);
        if (d >= minSep) continue;
        if (d < 0.001) {
          dx = ((i % 5) - 2) * 0.5 + 0.3;
          dy = ((j % 5) - 2) * 0.5 + 0.3;
          d = Math.hypot(dx, dy);
        }
        const push = (minSep - d) / 2;
        a.x -= (dx / d) * push;
        a.y -= (dy / d) * push;
        b.x += (dx / d) * push;
        b.y += (dy / d) * push;
        moved = true;
      }
    }
    for (const id of ids) {
      const p = pts.get(id)!;
      p.x = clamp(p.x, 40, W - 40);
      p.y = clamp(p.y, 30, H - 30);
    }
    if (!moved) break;
  }

  return pts;
}

/* -------------------------------------------------------------------------- */

function radiusFor(node: Node, degree: number, maxDegree: number, maxMem: number) {
  const byDegree = degree > 0 ? degree / maxDegree : 0;
  const byMem = maxMem > 0 ? (node.memory_count || 0) / maxMem : 0;
  return 7 + Math.max(byDegree, byMem) * 15;
}

export function EntityGraphView({ nodes, edges }: { nodes: Node[]; edges: Edge[] }) {
  const [selected, setSelected] = useState<Node | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [view, setView] = useState<"graph" | "table">("graph");
  const [expanded, setExpanded] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<string | null>(null);

  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<{ x: number; y: number; px: number; py: number } | null>(null);

  const degree = useMemo(() => {
    const d = new Map<string, number>();
    for (const e of edges) {
      d.set(e.source, (d.get(e.source) ?? 0) + 1);
      d.set(e.target, (d.get(e.target) ?? 0) + 1);
    }
    return d;
  }, [edges]);

  const maxDegree = Math.max(1, ...Array.from(degree.values()));
  const maxMem = Math.max(1, ...nodes.map((n) => n.memory_count || 0));

  const types = useMemo(
    () => Array.from(new Set(nodes.map((n) => n.entity_type))).sort(),
    [nodes],
  );

  // Positions depend only on structure, so they are stable across re-renders
  // and identical on server and client.
  const positions = useMemo(() => layout(nodes, edges), [nodes, edges]);

  const matches = useCallback(
    (n: Node) => {
      if (typeFilter && n.entity_type !== typeFilter) return false;
      if (!query.trim()) return true;
      const q = query.trim().toLowerCase();
      return (
        n.name.toLowerCase().includes(q) ||
        (n.summary ?? "").toLowerCase().includes(q) ||
        n.entity_type.toLowerCase().includes(q)
      );
    },
    [query, typeFilter],
  );

  /** When a node is active, only its direct neighbours stay lit. */
  const focusId = selected?.id ?? hovered;
  const neighbourhood = useMemo(() => {
    if (!focusId) return null;
    const s = new Set<string>([focusId]);
    for (const e of edges) {
      if (e.source === focusId) s.add(e.target);
      if (e.target === focusId) s.add(e.source);
    }
    return s;
  }, [focusId, edges]);

  const viewBox = `${W / 2 - W / (2 * zoom) + pan.x} ${H / 2 - H / (2 * zoom) + pan.y} ${
    W / zoom
  } ${H / zoom}`;

  const reset = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  // Wheel to zoom, drag to pan.
  useEffect(() => {
    const el = svgRef.current;
    if (!el || view !== "graph" || expanded) return;

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      setZoom((z) => Math.max(0.4, Math.min(3, z - e.deltaY * 0.0015)));
    };
    const onDown = (e: MouseEvent) => {
      if (e.button !== 0) return;
      dragRef.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y };
    };
    const onMove = (e: MouseEvent) => {
      const d = dragRef.current;
      if (!d) return;
      const scale = W / zoom / (el.clientWidth || W);
      setPan({
        x: d.px - (e.clientX - d.x) * scale,
        y: d.py - (e.clientY - d.y) * scale,
      });
    };
    const onUp = () => {
      dragRef.current = null;
    };

    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("mousedown", onDown);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("mousedown", onDown);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [zoom, pan.x, pan.y, view, expanded]);

  const selectedRelations = useMemo(
    () => (selected ? edges.filter((e) => e.source === selected.id || e.target === selected.id) : []),
    [edges, selected],
  );

  if (nodes.length === 0) {
    return (
      <div className="nb-card flex h-48 items-center justify-center text-[13px] text-muted-foreground">
        No entities extracted yet
      </div>
    );
  }

  const matchedCount = nodes.filter(matches).length;

  const toolbar = (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex overflow-hidden rounded-md border border-border">
        <button
          type="button"
          onClick={() => setView("graph")}
          className={`px-2.5 py-1.5 text-[13px] transition-colors ${
            view === "graph"
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-accent"
          }`}
        >
          Graph
        </button>
        <button
          type="button"
          onClick={() => setView("table")}
          className={`px-2.5 py-1.5 text-[13px] transition-colors ${
            view === "table"
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-accent"
          }`}
        >
          Table
        </button>
      </div>

      {view === "graph" && (
        <>
          <button onClick={() => setZoom((z) => Math.max(0.4, z - 0.3))} className="nb-btn nb-btn-ghost px-2" aria-label="Zoom out">
            &minus;
          </button>
          <button onClick={() => setZoom((z) => Math.min(3, z + 0.3))} className="nb-btn nb-btn-ghost px-2" aria-label="Zoom in">
            +
          </button>
          <button onClick={reset} className="nb-btn nb-btn-ghost">
            Reset
          </button>
        </>
      )}

      <div className="relative ml-1 min-w-[180px] flex-1 sm:max-w-[240px]">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter entities"
          className="nb-input h-8 pl-8 text-[13px]"
          aria-label="Filter entities"
        />
      </div>

      <span className="ml-auto text-[13px] tabular-nums text-muted-foreground">
        {matchedCount} / {nodes.length}
      </span>

      <button
        onClick={() => setExpanded((v) => !v)}
        className="nb-btn nb-btn-ghost px-2"
        aria-label={expanded ? "Exit full screen" : "Full screen"}
      >
        {expanded ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
      </button>
    </div>
  );

  const typeChips = (
    <div className="flex flex-wrap items-center gap-1.5">
      <button
        type="button"
        onClick={() => setTypeFilter(null)}
        className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
          typeFilter === null
            ? "border-[color:var(--input)] bg-accent text-foreground"
            : "border-border text-muted-foreground hover:bg-accent"
        }`}
      >
        all
      </button>
      {types.map((t) => (
        <button
          key={t}
          type="button"
          onClick={() => setTypeFilter(typeFilter === t ? null : t)}
          className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors ${
            typeFilter === t
              ? "border-[color:var(--input)] bg-accent text-foreground"
              : "border-border text-muted-foreground hover:bg-accent"
          }`}
        >
          <span
            className="size-2 rounded-full"
            style={{ background: TYPE_COLOR[t] ?? FALLBACK_COLOR }}
          />
          {t}
        </button>
      ))}
    </div>
  );

  const canvas =
    view === "graph" ? (
      <svg
        ref={svgRef}
        viewBox={viewBox}
        className="w-full cursor-grab rounded-lg border border-border bg-card active:cursor-grabbing"
        style={{ minHeight: 380, touchAction: "none" }}
        onDoubleClick={reset}
        role="img"
        aria-label={`Entity graph with ${nodes.length} entities`}
      >
        {/* Edges */}
        {edges.map((e, i) => {
          const a = positions.get(e.source);
          const b = positions.get(e.target);
          if (!a || !b) return null;
          const inFocus = neighbourhood ? neighbourhood.has(e.source) && neighbourhood.has(e.target) : true;
          const labelled = focusId && (e.source === focusId || e.target === focusId);
          return (
            <g key={i}>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="var(--border)"
                strokeWidth={labelled ? 2 : 1.25}
                opacity={inFocus ? 1 : 0.18}
              />
              {/* relationship_type was fetched but never rendered before */}
              {labelled && (
                <text
                  x={(a.x + b.x) / 2}
                  y={(a.y + b.y) / 2 - 4}
                  textAnchor="middle"
                  className="pointer-events-none select-none"
                  fill="var(--text-secondary)"
                  fontSize={10}
                >
                  {e.relationship_type.replace(/_/g, " ")}
                </text>
              )}
            </g>
          );
        })}

        {/* Nodes */}
        {nodes.map((n) => {
          const p = positions.get(n.id);
          if (!p) return null;
          const color = TYPE_COLOR[n.entity_type] ?? FALLBACK_COLOR;
          const r = radiusFor(n, degree.get(n.id) ?? 0, maxDegree, maxMem);
          const isMatch = matches(n);
          const inFocus = neighbourhood ? neighbourhood.has(n.id) : true;
          const isFocus = focusId === n.id;

          return (
            <g
              key={n.id}
              opacity={isMatch && inFocus ? 1 : 0.2}
              onMouseEnter={() => setHovered(n.id)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => setSelected(selected?.id === n.id ? null : n)}
              className="cursor-pointer"
            >
              {isFocus && (
                <circle cx={p.x} cy={p.y} r={r + 7} fill="none" stroke={color} strokeWidth={1.5} opacity={0.5} />
              )}
              <circle
                cx={p.x}
                cy={p.y}
                r={r}
                fill={color}
                stroke="var(--card)"
                strokeWidth={isFocus ? 2.5 : 1.5}
              />
              <text
                x={p.x}
                y={p.y + r + 13}
                textAnchor="middle"
                fill="var(--foreground)"
                fontSize={10.5}
                className="select-none"
              >
                {n.name.length > 16 ? n.name.slice(0, 15) + "…" : n.name}
              </text>
            </g>
          );
        })}
      </svg>
    ) : (
      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              {["Name", "Type", "Memories", "Links", "Summary"].map((h) => (
                <th key={h} className="p-2.5 text-left text-xs font-medium text-muted-foreground">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {nodes
              .filter(matches)
              .map((n) => (
                <tr
                  key={n.id}
                  onClick={() => setSelected(selected?.id === n.id ? null : n)}
                  className={`cursor-pointer border-b border-border transition-colors last:border-0 ${
                    selected?.id === n.id ? "bg-accent" : "hover:bg-accent"
                  }`}
                >
                  <td className="p-2.5">
                    <span className="flex items-center gap-2">
                      <span
                        className="size-2 shrink-0 rounded-full"
                        style={{ background: TYPE_COLOR[n.entity_type] ?? FALLBACK_COLOR }}
                      />
                      <span className="truncate font-medium">{n.name}</span>
                    </span>
                  </td>
                  <td className="p-2.5 text-[13px] text-muted-foreground">{n.entity_type}</td>
                  <td className="p-2.5 tabular-nums text-[13px] text-muted-foreground">
                    {n.memory_count}
                  </td>
                  <td className="p-2.5 tabular-nums text-[13px] text-muted-foreground">
                    {degree.get(n.id) ?? 0}
                  </td>
                  <td className="max-w-[220px] truncate p-2.5 text-[13px] text-muted-foreground">
                    {n.summary || "—"}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    );

  const body = (
    <div className="space-y-3">
      {toolbar}
      {typeChips}
      {canvas}

      {selected && (
        <div className="nb-card p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className="size-2.5 shrink-0 rounded-full"
                  style={{ background: TYPE_COLOR[selected.entity_type] ?? FALLBACK_COLOR }}
                />
                <h3 className="truncate text-sm font-semibold">{selected.name}</h3>
                <span className="nb-badge h-5 text-[11px]">{selected.entity_type}</span>
              </div>
              {selected.summary && (
                <p className="text-[13px] leading-relaxed text-muted-foreground">{selected.summary}</p>
              )}
              <p className="text-xs text-muted-foreground">
                {selected.memory_count} memor{selected.memory_count === 1 ? "y" : "ies"} ·{" "}
                {degree.get(selected.id) ?? 0} link{degree.get(selected.id) === 1 ? "" : "s"}
              </p>
              {selectedRelations.length > 0 && (
                <ul className="pt-1 text-[13px]">
                  {selectedRelations.slice(0, 6).map((e, i) => {
                    const otherId = e.source === selected.id ? e.target : e.source;
                    const other = nodes.find((n) => n.id === otherId);
                    return (
                      <li key={i} className="flex items-center gap-1.5">
                        <span className="text-muted-foreground">{e.relationship_type.replace(/_/g, " ")}</span>
                        <span className="text-[color:var(--text-tertiary)]">→</span>
                        <button
                          type="button"
                          onClick={() => setSelected(other ?? null)}
                          className="underline underline-offset-2 hover:text-[color:var(--accent-blue)]"
                        >
                          {other?.name ?? otherId.slice(0, 8)}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
            <button
              onClick={() => setSelected(null)}
              className="nb-btn nb-btn-ghost px-1.5"
              aria-label="Clear selection"
            >
              <X className="size-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );

  if (expanded) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col gap-3 p-6" style={{ background: "var(--background)" }}>
        <div className="flex-1 overflow-auto">{body}</div>
        <button onClick={() => setExpanded(false)} className="nb-btn nb-btn-secondary self-end">
          <Minimize2 className="size-4" /> Exit full screen
        </button>
      </div>
    );
  }

  return body;
}

"use client";

import { useMemo, useState } from "react";
import { Network, Maximize2 } from "lucide-react";
import Link from "next/link";

type GraphNode = {
  id: string;
  name: string;
  entity_type: string;
  memory_count?: number;
  summary?: string | null;
};

type GraphEdge = {
  source: string;
  target: string;
  relationship_type: string;
};

const COLORS: Record<string, string> = {
  person: "#3b82f6",
  topic: "#10b981",
  preference: "#f59e0b",
  organization: "#8b5cf6",
  location: "#ef4444",
};

const W = 380;
const H = 250;

function layout(nodes: GraphNode[]): Map<string, { x: number; y: number }> {
  const map = new Map<string, { x: number; y: number }>();
  const cx = W / 2;
  const cy = H / 2;
  const total = Math.max(nodes.length, 1);
  nodes.forEach((node, i) => {
    // Golden-angle spiral: deterministic, no overlap at the centre, and it keeps
    // working as the entity count grows.
    const angle = i * 2.399963;
    const radius = total === 1 ? 0 : 26 + (92 * Math.sqrt(i)) / Math.sqrt(total);
    map.set(node.id, { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius });
  });
  return map;
}

/**
 * Reads the live entity graph for the resolved actor. When the graph is empty
 * this renders an honest empty state rather than a decorative mock-up.
 */
export function MiniGraphPreview({
  nodes = [],
  edges = [],
  actorKnown = true,
  title = "Entity graph",
}: {
  nodes?: GraphNode[];
  edges?: GraphEdge[];
  /** False when the console could not resolve an actor UUID to query by. */
  actorKnown?: boolean;
  title?: string;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const positions = useMemo(() => layout(nodes), [nodes]);
  const selectedNode = nodes.find((n) => n.id === selected) ?? null;

  return (
    <div className="flex w-full flex-col justify-between rounded-lg border border-border bg-card p-5">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-normal text-foreground">
          <Network className="size-3.5 text-foreground/80" />
          <span>{title}</span>
        </div>
        <Link
          href="/dashboard/memories"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <span>Full Graph</span>
          <Maximize2 className="size-2.5 w-2.5" />
        </Link>
      </div>

      <p className="mb-3 text-xs text-muted-foreground">
        Multi-hop entity graph from the resolved actor, via{" "}
        <code className="font-mono">/v1/entities/graph/&lt;user_id&gt;</code>
      </p>

      {nodes.length === 0 ? (
        <div className="flex h-48 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-background/50 px-4 text-center text-xs text-muted-foreground">
          {actorKnown ? (
            <span>No entities extracted for this actor yet</span>
          ) : (
            <>
              <span>
                The graph is queried by actor, and the console could not resolve
                an actor UUID.
              </span>
              <span>
                The API resolves the actor from the bootstrap key but does not
                expose it. Set{" "}
                <code className="font-mono">CONTEXTA_DASHBOARD_USER_ID</code> or
                enter a user id in the sidebar organization panel.
              </span>
            </>
          )}
        </div>
      ) : (
        <div className="relative h-48 overflow-hidden rounded-lg border border-border bg-background/50">
          <div className="absolute inset-0 bg-[radial-gradient(#27272a_1px,transparent_1px)] [background-size:16px_16px] opacity-40" />
          <svg viewBox={`0 0 ${W} ${H}`} className="relative z-10 h-full w-full">
            {edges.map((edge, i) => {
              const a = positions.get(edge.source);
              const b = positions.get(edge.target);
              if (!a || !b) return null;
              const isConnected = selected === edge.source || selected === edge.target;
              return (
                <line
                  key={`${edge.source}-${edge.target}-${i}`}
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke={isConnected ? "#a1a1aa" : "#3f3f46"}
                  strokeWidth={isConnected ? 1.5 : 1}
                  strokeDasharray={isConnected ? "none" : "3,3"}
                  className="transition-colors duration-200"
                />
              );
            })}

            {nodes.map((node) => {
              const p = positions.get(node.id);
              if (!p) return null;
              const color = COLORS[node.entity_type] ?? "#6b7280";
              const isSelected = selected === node.id;
              return (
                <g
                  key={node.id}
                  className="group cursor-pointer"
                  onClick={() => setSelected(isSelected ? null : node.id)}
                >
                  <title>
                    {node.name} · {node.entity_type} · {node.memory_count ?? 0} memories
                  </title>
                  {isSelected ? (
                    <circle cx={p.x} cy={p.y} r={18} fill={color} opacity={0.15} />
                  ) : null}
                  <circle
                    cx={p.x}
                    cy={p.y}
                    r={isSelected ? 10 : 8}
                    fill="#1c1c21"
                    stroke={color}
                    strokeWidth={isSelected ? 2 : 1.5}
                  />
                  <text
                    x={p.x}
                    y={p.y + 18}
                    textAnchor="middle"
                    className="fill-muted-foreground text-[9px] transition-colors group-hover:fill-foreground"
                  >
                    {node.name.length > 16 ? `${node.name.slice(0, 15)}…` : node.name}
                  </text>
                </g>
              );
            })}
          </svg>

          {selectedNode ? (
            <div className="absolute bottom-2 left-2 z-20 flex items-center gap-2 rounded border border-border bg-card px-2.5 py-1 text-xs shadow-sm">
              <span
                className="size-2 rounded-full"
                style={{ backgroundColor: COLORS[selectedNode.entity_type] ?? "#6b7280" }}
              />
              <span className="text-foreground">{selectedNode.name}</span>
              <span className="text-muted-foreground">
                [{selectedNode.entity_type}] · {selectedNode.memory_count ?? 0} memories
              </span>
            </div>
          ) : null}
        </div>
      )}

      <div className="flex items-center justify-between pt-3 text-xs text-muted-foreground">
        <span>
          {nodes.length} {nodes.length === 1 ? "entity" : "entities"} · {edges.length}{" "}
          {edges.length === 1 ? "edge" : "edges"}
        </span>
        <span className="tone-green">Live from API</span>
      </div>
    </div>
  );
}

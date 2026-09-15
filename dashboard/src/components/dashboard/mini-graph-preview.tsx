"use client";

import { useState } from "react";
import { Network, Sparkles, Maximize2 } from "lucide-react";
import Link from "next/link";

interface GraphNode {
  id: string;
  label: string;
  type: string;
  x: number;
  y: number;
  color: string;
}

interface GraphEdge {
  source: string;
  target: string;
  label: string;
}

const NODES: GraphNode[] = [
  { id: "user", label: "User (Jenit)", type: "Identity", x: 190, y: 110, color: "#6366f1" },
  { id: "role", label: "Autonomous Pair", type: "Role", x: 90, y: 50, color: "#10b981" },
  { id: "stack", label: "TypeScript / Go", type: "Stack", x: 290, y: 55, color: "#38bdf8" },
  { id: "vault", label: "AES-Vault", type: "Security", x: 100, y: 175, color: "#f59e0b" },
  { id: "model", label: "Qwen3-Offline", type: "Engine", x: 285, y: 170, color: "#ec4899" },
  { id: "mcp", label: "MCP Daemon", type: "Protocol", x: 190, y: 220, color: "#8b5cf6" },
];

const EDGES: GraphEdge[] = [
  { source: "user", target: "role", label: "ASSIGNS" },
  { source: "user", target: "stack", label: "PREFERS" },
  { source: "user", target: "vault", label: "SECURES" },
  { source: "user", target: "model", label: "QUERIES" },
  { source: "vault", target: "mcp", label: "FEEDS" },
  { source: "model", target: "mcp", label: "SERVES" },
];

export function MiniGraphPreview({
  title = "Entity & Knowledge Mesh",
}: {
  title?: string;
}) {
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(NODES[0]);

  return (
    <div className="w-full rounded-xl border border-border/40 bg-card/60 p-5 font-mono flex flex-col justify-between">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-xs font-normal text-foreground">
          <Network className="h-3.5 w-3.5 text-foreground/80" />
          <span>{title}</span>
        </div>
        <Link
          href="/dashboard/memories"
          className="text-[10px] text-muted-foreground hover:text-foreground inline-flex items-center gap-1 transition-colors"
        >
          <span>Full Graph</span>
          <Maximize2 className="h-2.5 w-2.5" />
        </Link>
      </div>

      <p className="text-[10px] text-muted-foreground mb-3">
        Cross-observation multi-hop entity graph synthesized in real-time
      </p>

      {/* SVG Canvas */}
      <div className="relative w-full h-48 bg-background/50 rounded-lg border border-border/30 overflow-hidden flex items-center justify-center">
        {/* Subtle grid background */}
        <div className="absolute inset-0 bg-[radial-gradient(#27272a_1px,transparent_1px)] [background-size:16px_16px] opacity-40" />

        <svg viewBox="0 0 380 250" className="w-full h-full relative z-10">
          {/* Edges */}
          {EDGES.map((edge, i) => {
            const src = NODES.find((n) => n.id === edge.source);
            const tgt = NODES.find((n) => n.id === edge.target);
            if (!src || !tgt) return null;

            const isConnected =
              selectedNode &&
              (selectedNode.id === edge.source || selectedNode.id === edge.target);

            return (
              <g key={i}>
                <line
                  x1={src.x}
                  y1={src.y}
                  x2={tgt.x}
                  y2={tgt.y}
                  stroke={isConnected ? "#a1a1aa" : "#3f3f46"}
                  strokeWidth={isConnected ? 1.5 : 1}
                  strokeDasharray={isConnected ? "none" : "3,3"}
                  className="transition-colors duration-200"
                />
              </g>
            );
          })}

          {/* Nodes */}
          {NODES.map((node) => {
            const isSelected = selectedNode?.id === node.id;
            return (
              <g
                key={node.id}
                className="cursor-pointer group"
                onClick={() => setSelectedNode(node)}
              >
                {/* Glow circle if selected */}
                {isSelected && (
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={18}
                    fill={node.color}
                    opacity={0.15}
                    className="animate-pulse"
                  />
                )}
                {/* Node circle */}
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={isSelected ? 10 : 8}
                  fill="#1c1c21"
                  stroke={node.color}
                  strokeWidth={isSelected ? 2 : 1.5}
                  className="transition-all duration-200"
                />
                {/* Node text */}
                <text
                  x={node.x}
                  y={node.y + 18}
                  textAnchor="middle"
                  className="text-[9px] fill-muted-foreground group-hover:fill-foreground font-mono transition-colors select-none"
                >
                  {node.label}
                </text>
              </g>
            );
          })}
        </svg>

        {/* Selected Node Inspector Badge */}
        {selectedNode && (
          <div className="absolute bottom-2 left-2 z-20 flex items-center gap-2 rounded border border-border/40 bg-card/90 px-2.5 py-1 text-[10px] backdrop-blur-md shadow-sm">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: selectedNode.color }}
            />
            <span className="text-foreground">{selectedNode.label}</span>
            <span className="text-muted-foreground">[{selectedNode.type}]</span>
          </div>
        )}
      </div>

      {/* Footer Info */}
      <div className="flex items-center justify-between pt-3 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-1">
          <Sparkles className="h-3 w-3 text-indigo-400" />
          <span>6 Active Nodes • 6 Resolved Edges</span>
        </span>
        <span className="text-emerald-400">Deterministic Lineage</span>
      </div>
    </div>
  );
}

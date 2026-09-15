"use client";

import React, { useRef, useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { motion } from "framer-motion";

type NodeType = "core" | "entity" | "fact" | "vector";

interface LatticeNode {
  x: number;
  y: number;
  baseZ: number;
  type: NodeType;
  links: number[];
  phase: number;
  speed: number;
  size: number;
}

interface LatticeLink {
  from: number;
  to: number;
  strength: number;
  animated: boolean;
  progress: number;
}

const NODE_COLORS: Record<NodeType, { fill: string; glow: string }> = {
  core: { fill: "#3B82F6", glow: "rgba(59,130,246,0.55)" },
  entity: { fill: "#8B5CF6", glow: "rgba(139,92,246,0.5)" },
  fact: { fill: "#10B981", glow: "rgba(16,185,129,0.5)" },
  vector: { fill: "#06B6D4", glow: "rgba(6,182,212,0.5)" },
};

const GRID = 26;
const SPACING = 44;
const PAD = 60;

export function HeroScene() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nodesRef = useRef<LatticeNode[]>([]);
  const linksRef = useRef<LatticeLink[]>([]);
  const mouseRef = useRef({ x: -9999, y: -9999 });
  const hoverRef = useRef<number | null>(null);
  const rafRef = useRef<number>(0);
  const timeRef = useRef(0);
  const [, setHover] = useState<number | null>(null);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const h = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, []);

  const build = useCallback((w: number, h: number) => {
    const nodes: LatticeNode[] = [];
    const cx = w / 2;
    const cy = h / 2;
    const offY = ((GRID - 1) * SPACING * 0.25) / 2 + 20;

    for (let gx = 0; gx < GRID; gx++) {
      for (let gy = 0; gy < GRID; gy++) {
        const isoX = (gx - gy) * (SPACING * 0.5);
        const isoY = (gx + gy) * (SPACING * 0.25);
        const sx = cx + isoX;
        const sy = cy + isoY - offY;
        if (sx < PAD || sx > w - PAD || sy < PAD || sy > h - PAD) continue;
        const dcx = gx - GRID / 2;
        const dcy = gy - GRID / 2;
        const dist = Math.sqrt(dcx * dcx + dcy * dcy);
        let type: NodeType = "vector";
        let baseZ = Math.random() * 2;
        let size = 1.8 + Math.random() * 0.8;
        if (dist < 1.6) {
          type = "core";
          baseZ = 8;
          size = 4.5;
        } else if (dist < 4.5) {
          type = Math.random() > 0.5 ? "entity" : "fact";
          baseZ = 2 + Math.random() * 4;
          size = 2.4 + Math.random() * 1.4;
        }
        nodes.push({
          x: sx,
          y: sy,
          baseZ,
          type,
          links: [],
          phase: Math.random() * Math.PI * 2,
          speed: 0.5 + Math.random() * 1.4,
          size,
        });
      }
    }

    nodes.forEach((n, i) => {
      const nb: number[] = [];
      nodes.forEach((o, j) => {
        if (i === j) return;
        const dx = n.x - o.x;
        const dy = n.y - o.y;
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d < SPACING * 1.35 && Math.random() > 0.72) nb.push(j);
      });
      n.links = nb.slice(0, 3);
    });

    const links: LatticeLink[] = [];
    nodes.forEach((n, i) => {
      n.links.forEach((j) => {
        if (i < j && j < nodes.length) {
          links.push({
            from: i,
            to: j,
            strength: 0.4 + Math.random() * 0.6,
            animated: Math.random() > 0.86,
            progress: Math.random(),
          });
        }
      });
    });

    nodesRef.current = nodes;
    linksRef.current = links;
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !canvas.parentElement) return;
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const rect = canvas.parentElement!.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
      const ctx = canvas.getContext("2d");
      if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      build(rect.width, rect.height);
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [build]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    if (reduced) {
      // single static frame
      const w = canvas.width / (Math.min(window.devicePixelRatio || 1, 2));
      const h = canvas.height / (Math.min(window.devicePixelRatio || 1, 2));
      ctx.clearRect(0, 0, w, h);
      nodesRef.current.forEach((n) => {
        ctx.fillStyle = NODE_COLORS[n.type].fill;
        ctx.globalAlpha = 0.7;
        ctx.beginPath();
        ctx.arc(n.x, n.y - n.baseZ, n.size, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.globalAlpha = 1;
      return;
    }

    let last = performance.now();
    const loop = (now: number) => {
      const dt = Math.min(now - last, 50);
      last = now;
      const t = now * 0.001;
      timeRef.current = t;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = canvas.width / dpr;
      const h = canvas.height / dpr;
      ctx.clearRect(0, 0, w, h);

      const nodes = nodesRef.current;
      const links = linksRef.current;
      const dyn = nodes.map((n, i) => {
        const pulse = Math.sin(t * n.speed + n.phase) * 0.3 + 0.7;
        const zp = Math.sin(t * 0.35 + i * 0.08) * 2;
        const dx = mouseRef.current.x - n.x;
        const dy = mouseRef.current.y - n.y;
        const md = Math.sqrt(dx * dx + dy * dy);
        const infl = md < 150 ? (1 - md / 150) * 5 : 0;
        return {
          ...n,
          z: n.baseZ + zp + infl,
          r: n.size * pulse * (hoverRef.current === i ? 1.6 : 1),
          glow: hoverRef.current === i ? 1 : pulse * 0.55,
        };
      });
      const order = dyn.map((_, i) => i).sort((a, b) => dyn[a].z - dyn[b].z);

      links.forEach((l) => {
        const a = dyn[l.from];
        const b = dyn[l.to];
        if (!a || !b) return;
        const alpha = l.strength * 0.16;
        const grad = ctx.createLinearGradient(a.x, a.y - a.z, b.x, b.y - b.z);
        grad.addColorStop(0, `rgba(59,130,246,${alpha})`);
        grad.addColorStop(0.5, `rgba(139,92,246,${alpha * 0.8})`);
        grad.addColorStop(1, `rgba(6,182,212,${alpha})`);
        ctx.strokeStyle = grad;
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y - a.z);
        ctx.lineTo(b.x, b.y - b.z);
        ctx.stroke();
        if (l.animated) {
          l.progress = (l.progress + dt * 0.00035) % 1;
          const pp = Math.sin(l.progress * Math.PI * 2) * 0.5 + 0.5;
          const px = a.x + (b.x - a.x) * pp;
          const py = a.y + (b.y - a.y) * pp - (a.z + (b.z - a.z) * pp);
          ctx.fillStyle = `rgba(96,165,250,${0.55 * pp})`;
          ctx.beginPath();
          ctx.arc(px, py, 1.8, 0, Math.PI * 2);
          ctx.fill();
        }
      });

      order.forEach((i) => {
        const n = dyn[i];
        const c = NODE_COLORS[n.type];
        const x = n.x;
        const y = n.y - n.z;
        if (n.glow > 0.3) {
          const g = ctx.createRadialGradient(0, 0, 0, 0, 0, n.r * 4 * n.glow);
          g.addColorStop(0, c.glow);
          g.addColorStop(1, "rgba(0,0,0,0)");
          ctx.save();
          ctx.translate(x, y);
          ctx.fillStyle = g;
          ctx.beginPath();
          ctx.arc(0, 0, n.r * 4 * n.glow, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        }
        ctx.fillStyle = c.fill;
        ctx.beginPath();
        ctx.arc(x, y, n.r, 0, Math.PI * 2);
        ctx.fill();
      });

      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [reduced]);

  const onMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    mouseRef.current = { x: mx, y: my };
    let best = -1;
    let bd = 30;
    nodesRef.current.forEach((n, i) => {
      const d = Math.hypot(mx - n.x, my - n.y);
      if (d < bd) {
        bd = d;
        best = i;
      }
    });
    hoverRef.current = best === -1 ? null : best;
    setHover(hoverRef.current);
  };

  const onLeave = () => {
    mouseRef.current = { x: -9999, y: -9999 };
    hoverRef.current = null;
    setHover(null);
  };

  return (
    <div className="relative w-full aspect-[16/9] max-w-[1000px] mx-auto rounded-2xl sm:rounded-3xl overflow-hidden bg-[#050507] shadow-elev-3">
      <canvas
        ref={canvasRef}
        className="hero-canvas"
        aria-hidden="true"
        onMouseMove={onMove}
        onMouseLeave={onLeave}
      />
      <div className="absolute inset-0 bg-gradient-to-t from-[#050507]/70 via-transparent to-transparent pointer-events-none" />
      {!reduced && <div className="absolute inset-0 opacity-[0.02] iso-grid-pattern pointer-events-none" />}
    </div>
  );
}

export function HeroSection() {
  const [visible, setVisible] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 80);
    return () => clearTimeout(t);
  }, []);

  const copyInstall = () => {
    try {
      navigator.clipboard.writeText("pip install contexta");
    } catch {
      /* clipboard unavailable */
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <section className="relative flex flex-col items-center text-center pt-20 pb-10 lg:pt-28 lg:pb-14 space-y-7">
      <motion.div
        className="inline-flex items-center gap-2.5 px-4 py-1.5 rounded-full bg-white/[0.03] backdrop-blur-xl text-xs font-mono text-[#6B7280] shadow-elev-1"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
        <span>50,000 AGENT MEMORY SCALE BENCHMARK READY</span>
        <span className="text-white/20">|</span>
        <a href="#benchmarks" className="text-blue-400 font-medium hover:underline inline-flex items-center gap-1">
          View Graph <span aria-hidden="true">→</span>
        </a>
      </motion.div>

      <motion.h1
        className="text-display text-4xl sm:text-6xl lg:text-7xl tracking-tight text-white max-w-5xl leading-[1.06]"
        initial={{ opacity: 0, y: 30 }}
        animate={visible ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
      >
        The memory plane for
        <br />
        <span className="font-normal bg-gradient-to-r from-blue-400 via-sky-300 to-indigo-400 bg-clip-text text-transparent">
          autonomous AI agents.
        </span>
      </motion.h1>

      <motion.p
        className="max-w-2xl text-base sm:text-lg font-light leading-relaxed text-[#6B7280]"
        initial={{ opacity: 0, y: 20 }}
        animate={visible ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.8, delay: 0.35, ease: [0.16, 1, 0.3, 1] }}
      >
        Contexta parses multi-turn dialogue into continuous, graph-relational facts.
        Ground your copilots with sub-180ms p95 recall, zero memory drift, and
        cryptographic tenant isolation enclaves.
      </motion.p>

      <motion.div
        className="flex flex-wrap gap-3.5 justify-center items-center pt-2"
        initial={{ opacity: 0, y: 20 }}
        animate={visible ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.8, delay: 0.5, ease: [0.16, 1, 0.3, 1] }}
      >
        <Link href="/sign-up" className="btn-primary">
          <span>Deploy Free Enclave</span>
          <span aria-hidden="true">→</span>
        </Link>
        <button onClick={copyInstall} className="btn-secondary" aria-label="Copy install command">
          <svg className="w-4 h-4 text-blue-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <rect x="2" y="3" width="20" height="14" rx="2" />
            <path d="M8 21h8M12 17v4" />
          </svg>
          <span>pip install contexta</span>
          <span className="text-[10px] text-[#3D4450]">{copied ? "copied" : "copy"}</span>
        </button>
      </motion.div>

      <motion.div
        className="w-full pt-4"
        initial={{ opacity: 0, y: 30 }}
        animate={visible ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 1, delay: 0.65, ease: [0.16, 1, 0.3, 1] }}
      >
        <HeroScene />
      </motion.div>
    </section>
  );
}

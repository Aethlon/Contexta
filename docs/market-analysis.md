# Contexta — Memory Layer Market Analysis (August 2026)

## 1. Market Summary

The agent-memory ("memory layer") category sells **persistent memory between LLM context windows**: extraction of facts/preferences/episodes from conversations, structured storage, and retrieval at prompt time. It exists because agents are stateless by default, and naive solutions (shoving full transcripts into the prompt) break down at scale.

Key players:

- **Managed memory APIs**: Mem0 (mem0.ai), Zep (getzep.com), Letta (letta.com).
- **Open-source / DIY**: Mem0 OSS, Cognee, LangChain LangMem, Memori, Basic Memory, and raw DIY stacks built on `pgvector`.

The dominant trend cuts **in Contexta's favor**: longer context windows make *selective* memory **more** valuable, not less. As context grows, attention degrades ("lost in the middle") and token costs rise superlinearly with prompt size. A memory layer that injects only high-utility, truth-maintained context into the prompt is the standard mitigation — this is exactly the pipeline Contexta ships (extract → dedupe → score → decay → retrieve), per `contexta/core/pipeline.py` and the modules under `contexta/core/`.

## 2. Competitor Pricing (from competitor websites, fetched Aug 2026)

### Mem0 (mem0.ai)

| Tier | Price | Limits |
|---|---|---|
| Free | $0 | 10k add requests/mo, 1k retrievals/mo, 1 project |
| Starter | $19/mo | 50k adds, 5k retrievals, 1 project |
| Pro | $249/mo | 500k adds, 50k retrievals, unlimited projects, graph memory, "Dream" consolidation, private Slack |
| Enterprise | Custom | On-prem, audit logs, SSO, SLA |

Open-source core (~62k GitHub stars). Claims SOC 2 Type I and HIPAA-readiness.

### Zep (getzep.com)

| Tier | Price | Limits |
|---|---|---|
| Free | $0 | 10k credits/mo |
| Flex | $125/mo ($104/mo annual) | 50k credits, overage $25/10k credits, 600 req/min, 5 projects |
| Flex Plus | $375/mo ($312/mo annual) | 200k credits, 1,000 req/min, observations, webhooks, analytics |
| Enterprise | Custom | — |

1 credit = 1 Episode per 350 bytes ingested; retrieval, storage, and users are unmetered. SOC 2 Type II, HIPAA BAA, BYOK, BYOC/VPC. "Emerging Companies" program at $13k/yr.

### Letta (letta.com)

| Tier | Price |
|---|---|
| Free | 3 agents, BYOK |
| Pro | $20/mo |
| API plan | $20/mo + $0.10/active agent/mo + $0.00015/sec tool execution |
| Teams Pro | $20/seat |
| Enterprise | Custom |

Letta is an agent framework with built-in memory (MemGPT lineage) — **adjacent category**, more competitor-to-ecosystem than direct, but relevant for agents that want memory "in the framework."

### Open-source / DIY

| Option | License | Cost | Notes |
|---|---|---|---|
| Mem0 OSS | Apache-2.0 | $0 + self-host | No managed dream/reflection |
| Cognee | Open source | $0 + self-host | Graph-oriented, ETL-heavy |
| LangChain LangMem | Open source | $0 + self-host | Tight to LangChain |
| Memori | Open source | $0 + self-host | |
| Basic Memory | Open source | $0 + self-host | File-based, personal use |
| DIY (pgvector) | n/a | Engineering time | No lifecycle, no truth maintenance |

## 3. Contexta Pricing Positioning

**BYOK platform fee** — Contexta charges a platform fee and never resells tokens; customers bring their own OpenAI/Anthropic keys (decision of record in `Business plan/01-pricing-and-unit-economics.md`). This is unique in the category: competitors sell credits (Zep) or meter requests (Mem0), which makes their revenue LLM-pass-through-heavy and their price per unit of memory opaque. Contexta's fee covers storage, retrieval infrastructure, dashboard, reflection, dream cycle, and support.

| Tier | Price | Notes |
|---|---|---|
| Free | $0 | 10k memories, 25k observations/mo — **new, recommended** (not in original launch plan) |
| Hobby | $19/mo | Solo devs, 1 project |
| Solo Pro | $69/mo | Indie devs shipping a product |
| Team | $499/mo | SSO (Google/GitHub), unlimited schemas, 20+ projects |
| Scale | $2,999/mo | High-volume production; low-margin relationship tier |
| Enterprise | $5k–$25k+/mo | Dedicated infra, VPC peering, BAA, SOC 2 reporting, custom regions |

Overage model (from business planning; rates match `docs/src/app/pricing/page.mdx`): observations $0.002 each, retrievals $0.0001 each, reranks $0.003 each, storage $0.50 per 1k memories/mo.

> ⚠️ Alignment flag: `docs/src/app/pricing/page.mdx` still lists the older Builder $29 / Scale $99 / Dedicated $299+ structure. Align it with the launch plan (Free/Hobby/Solo Pro/Team/Scale/Enterprise) before it ships.

## 4. How Contexta Differs

| Capability | Contexta | Mem0 | Zep | Letta |
|---|---|---|---|---|
| Truth maintenance (contradiction detection, supersession, versioned facts) | **Shipped** (`contexta/core/truth/maintenance.py`) | ✗ | ✗ | ✗ |
| Sensitive-data redaction at ingestion (passwords, API keys, JWTs, cards via Luhn, OTPs, cookies) | **Shipped** (`contexta/core/extraction/sensitive_filter.py`, on by default) | Partial | Partial | ✗ |
| Memory explainability (supersession history, audit trail, score breakdowns) | **Shipped**: `MemoryVersion` chain + `memory_superseded` audit events; scores decompose into semantic/graph/importance/recency/keyword (`contexta/core/retrieval/engine.py`) | Limited | Limited | Limited |
| Token-aware context planner (budget across projects/goals/facts/episodic/preferences/relationships) | **Shipped** (`contexta/core/context/planner.py`) | ✗ | Partial | Partial |
| Tenant isolation | API tenant middleware + org-scoped repos + cross-tenant tests (`contexta/api/middleware/tenant.py`, `tests/`); **Postgres RLS: roadmap** | Per-project | Per-project | Per-user |
| Hybrid retrieval, cluster-aware | **Shipped**: semantic + keyword + graph + importance + recency; semantic clustering (min 3 members) feeds cluster-aware planning | Graph on Pro | Graph | ✗ |
| Sub-100ms p99 @ 1M memories/tenant | **Target** (roadmap benchmark; Go data-plane already claims <10ms read/write path per `README.md`) | Unverified | Unverified | n/a |
| BYOK + platform fee pricing | **Shipped** (decision of record) | ✗ (credits/requests) | ✗ (credits) | ✗ (BYOK but framework-bound) |
| Adapters | **Shipped**: OpenAI, Anthropic, LangChain, LlamaIndex (Python); OpenAI, Anthropic, LangChain, Vercel AI (TypeScript) — see `clients/` | OpenAI/LangChain | LangChain | Built-in |

**No competitor ships automatic contradiction detection/resolution with versioned facts** — the truth-maintenance engine (`contexta/core/truth/maintenance.py` + `contexta/models/version.py`) is the clearest feature-led differentiation. Deduplication (discard ≥ 0.95, merge ≥ 0.85) and decay (30/90/180-day thresholds in `contexta/config/settings.py`) round out a lifecycle stack competitors only partially cover.

## 5. Gaps & Risks

| Gap/Risk | Detail | Mitigation |
|---|---|---|
| No free tier at original launch | Original plan was paid-only (per `Business plan/01`) — all competitors have a free tier | **Add Free tier** (10k memories / 25k observations) — already recommended in current plan |
| $19 Hobby price-identical to Mem0 Starter | Same price point as the market leader | Differentiation must be feature-led (truth maintenance, redaction, explainability) |
| Team $499 vs Mem0 Pro $249 | Nearly 2x the headline "pro" price | Justify in copy: SSO, unlimited schemas, RLS, retention, audit — not just limits |
| Scale $2,999 thin-margin | ~7% gross margin at 80% utilization (per `Business plan/01`) | Position as relationship tier that converts to Enterprise within 12 months |
| Distribution risk | Mem0's ~62k GitHub stars are a primary acquisition channel; Contexta has no comparable OSS funnel | Open-source repo + MCP server + published benchmarks; see `opensource-strategy.md` |
| Benchmark gap | Nobody in the category quantifies retrieval quality; "memory quality" claims are unverifiable | Publish LoCoMo-style retrieval benchmarks to make quality a first-class purchasing criterion |

## 6. Recommendations

1. **Launch the Free tier** — table stakes; every competitor has one.
2. **Publish SDKs to PyPI (`contexta-client`) and npm (`@contexta/client`)** — currently local-only in `clients/`.
3. **Ship an MCP server** — the distribution channel AI-agent developers now default to (roadmap; not yet in repo).
4. **Pick 1–2 vertical wedges** — the CRM agent (`clients/examples/anthropic-crm/`) is the obvious first; support and sales bots second.
5. **Treat SOC 2, audit logs, EU residency as product features**, not paperwork — they are the Team/Enterprise conversion lever against Mem0's tier cap.
6. **Publish a benchmark report** (retrieval quality, latency at scale) — turns the "sub-100ms @ 1M memories" target from a claim into a proof.

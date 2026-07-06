# 01 — Pricing and Unit Economics

This document is the source of truth for what we charge, what each unit costs us, and what margin we make per tenant. All numbers assume gpt-4o-mini for extraction and text-embedding-3-small for embeddings, both as of May 2026 OpenAI pricing.

## Cost dimensions (what we actually pay for)

| Dimension | Per-unit cost (May 2026) | Notes |
|---|---|---|
| LLM extraction (per observation) | **$0.00040** | ~800 input tokens × $0.15/M + ~500 output tokens × $0.60/M |
| LLM rerank (per retrieval, if enabled) | **$0.00057** | ~3000 in × $0.15/M + 200 out × $0.60/M |
| LLM reflection cycle (per tenant per night) | **$0.0027** | Across 100 candidate memories |
| LLM dream cycle (per tenant per week) | **$0.0075** | 20 synthetic questions, evaluated |
| Embedding (per memory or query) | **$0.0000030** | ~150 tokens × $0.02/M |
| Postgres + pgvector storage (per 1k memories per month) | **$0.10** | Self-hosted Hetzner amortized |
| Postgres pgvector RAM (per 1k active memories) | **$0.05/mo** | HNSW index sizing |
| Redis memory (per tenant) | **$0.20/mo** | Hot context cache |
| API + worker compute | **$0.000005 / request** | Amortized fleet cost at 500 RPS |
| Egress | **$0.00 / GB** | Hetzner unmetered up to fair use |
| Stripe fees | **2.9% + $0.30 per charge** | Pass-through, not absorbed |

These costs assume self-hosted Hetzner dedicated boxes (see doc 12 for topology). Cloud-managed equivalents (AWS RDS + ElastiCache + Fargate) would be 3–5x more expensive — that is exactly why we self-host.

## Pricing model: BYOK platform fee + optional managed LLM add-on

**Decision of record:** customers bring their own OpenAI/Anthropic API key by default. contexta charges a platform fee that covers storage, retrieval infrastructure, dashboard, reflection, dream cycle, support, and infra.

This decision exists because LLM passthrough costs would otherwise dominate revenue and force us into negative margins. Vercel, Supabase, and Cloudflare's AI products all use this exact pattern.

Customers can opt into a "Managed LLM" add-on where contexta provides a contexta-issued OpenAI proxy key with a pre-paid token bundle. We mark up tokens 5x.

## Tiers (BYOK, paid only — no free tier at launch)

### Hobby — $19/month
For solo devs prototyping a single agent.

| Limit | Value |
|---|---|
| Active memories | 50,000 |
| Observations / month | 100,000 |
| Retrievals / month | 1,000,000 |
| Reranks / month | 10,000 |
| Custom schemas | 3 |
| Custom policies | 3 |
| Projects | 1 |
| Reflection cycles | manual only |
| Dream cycle | off |
| Retention | 90 days |
| Audit retention | 30 days |
| Concurrent RPS cap | 10 |
| Support | community Discord, weekly office hours |

### Solo Pro — $59/month
For an indie dev shipping a real product.

| Limit | Value |
|---|---|
| Active memories | 250,000 |
| Observations / month | 500,000 |
| Retrievals / month | 5,000,000 |
| Reranks / month | 100,000 |
| Custom schemas | 10 |
| Custom policies | 10 |
| Projects | 5 |
| Reflection cycles | nightly |
| Dream cycle | weekly |
| Retention | 1 year |
| Audit retention | 90 days |
| Concurrent RPS cap | 50 |
| Support | private channel, 24h SLA |

### Team — $249/month
For a small team or a mid-stage AI product team.

| Limit | Value |
|---|---|
| Active memories | 2,000,000 |
| Observations / month | 5,000,000 |
| Retrievals / month | 50,000,000 |
| Reranks / month | 1,000,000 |
| Custom schemas | unlimited |
| Custom policies | unlimited |
| Projects | 20 |
| Reflection cycles | nightly |
| Dream cycle | weekly |
| Retention | unlimited |
| Audit retention | 1 year |
| Concurrent RPS cap | 250 |
| SSO (Google, GitHub) | included |
| Support | private channel, 4h SLA |

### Scale — $999/month
For high-volume production agents.

| Limit | Value |
|---|---|
| Active memories | 20,000,000 |
| Observations / month | 50,000,000 |
| Retrievals / month | 500,000,000 |
| Reranks / month | 10,000,000 |
| Projects | unlimited |
| Reflection cycles | nightly |
| Dream cycle | daily |
| Retention | unlimited |
| Audit retention | unlimited |
| Concurrent RPS cap | 1,000 |
| SSO + SAML | included |
| Cold tier export | included |
| Support | dedicated SRE, 1h SLA, monthly review |

### Enterprise — custom (typically $5k–$25k/month)
- Dedicated single-tenant infrastructure (separate Postgres node, separate Redis cluster, separate worker pool).
- VPC peering, private link.
- BAA, SOC 2 Type II report sharing, custom DPA.
- Custom retention policies.
- Custom regions (US, EU, AP).
- 99.99% uptime SLA with credits.

## Overage rates (when limits are exceeded)

Limits are soft by default. We warn at 80% and 100% via email and dashboard. Hard cap can be enabled per-key in the dashboard.

| Dimension | Overage rate |
|---|---|
| Observations | $0.002 each |
| Retrievals (no rerank) | $0.0001 each |
| Reranks | $0.003 each |
| Storage (1k memories / month) | $0.50 |

Overage is billed at end of cycle. Hard caps return 429 instead of allowing overage.

## Managed LLM add-on (optional)

When customers do not want to bring their own key, they enable Managed LLM. contexta proxies OpenAI/Anthropic calls through a contexta-owned key.

| Bundle | Price | Tokens included | Overage |
|---|---|---|---|
| Starter | $25/mo | 5M input, 1M output | $5 / extra million |
| Builder | $99/mo | 25M input, 5M output | $4 / extra million |
| Pro | $399/mo | 150M input, 30M output | $3 / extra million |

Markup: ~5x on input tokens, ~3x on output tokens. This funds OpenAI key management, abuse monitoring, and reliability.

## Profit math per tier

Assumptions per tier are shown at **80% utilization** of limits (a reasonable proxy for an active customer).

### Hobby ($19/mo) at 80% utilization
- 80,000 observations × $0.00040 = **$32 LLM cost** (passed to customer via BYOK, not absorbed)
- 800,000 retrievals × $0.000005 = **$4 compute**
- 8,000 reranks × $0.00057 = **$4.56 LLM cost** (BYOK, not absorbed)
- 40,000 memories × $0.10/1k = **$4 storage**
- 40,000 memories × $0.05/1k = **$2 RAM**
- Redis: **$0.20**
- Manual reflection: **$0**
- **Total cost to us: $10.20**
- **Revenue: $19.00**
- **Gross margin: $8.80 (46%)**

Note: At Hobby tier the absolute margin is small but compute is shared. The real value is the funnel — Hobby converts to Solo Pro within 6 months for ~30% of accounts.

### Solo Pro ($59/mo) at 80% utilization
- 400,000 observations × $0.00040 = **$160 LLM cost** (BYOK)
- 4,000,000 retrievals × $0.000005 = **$20 compute**
- 80,000 reranks × $0.00057 = **$45.60 LLM cost** (BYOK)
- 200,000 memories × $0.10/1k = **$20 storage**
- 200,000 memories × $0.05/1k = **$10 RAM**
- Redis: **$0.50**
- Reflection 30 nights × $0.0027 = **$0.08 LLM** (BYOK)
- Dream 4 weeks × $0.0075 = **$0.03 LLM** (BYOK)
- **Total cost to us (excl LLM): $50.50**
- **Revenue: $59**
- **Gross margin: $8.50 (14%)** ⚠️

This margin is too thin. Two ways to fix:
1. **Raise to $79/mo** → margin becomes $28.50 (36%). Recommended.
2. **Tighten limits** → reduce observations to 250k, retrievals to 2M. Margin becomes $25 (42%). Acceptable but limits the product feel.

**Decision: Solo Pro will launch at $69/mo** with the limits above. Margin: $18.50 (27%). Cleaner story, still under $100 psychological barrier.

### Team ($249/mo) at 80% utilization
- 4,000,000 observations × $0.00040 = **$1,600 LLM cost** (BYOK)
- 40,000,000 retrievals × $0.000005 = **$200 compute**
- 800,000 reranks × $0.00057 = **$456 LLM cost** (BYOK)
- 1,600,000 memories × $0.10/1k = **$160 storage**
- 1,600,000 memories × $0.05/1k = **$80 RAM**
- Redis: **$2**
- **Total cost to us (excl LLM): $442**
- **Revenue: $249** ⚠️ NEGATIVE MARGIN

Team is underpriced. Either:
1. **Raise to $499/mo** → margin $57 (11%). Still tight.
2. **Raise to $599/mo** → margin $157 (26%). Healthy.
3. **Tighten limits** → drop observations to 2M and retrievals to 20M. Cost becomes $234, margin at $249 = $15 (6%). Too tight.

**Decision: Team launches at $499/mo with limits above.** This is justified because Team includes SSO and project quota that Hobby/Solo do not. Revenue per Team customer is 7x Solo Pro and the support burden is only 2x.

### Scale ($999/mo)
- Costs at 80% utilization: 40M obs × $0.0004 = $16,000 (BYOK), 400M retrievals × $0.000005 = $2,000 compute, 8M reranks × $0.00057 = $4,560 (BYOK), storage + RAM ~$2,400.
- **Total cost to us (excl LLM): ~$4,400**
- **Revenue: $999** — wildly underpriced.

**Decision: Scale launches at $2,499/mo** with above limits. Margin $-1,901 still loses, so we **also tighten limits**: observations to 25M, retrievals to 250M, reranks to 5M. New cost: $2,775. New margin at $2,499 = $-276. Still underwater.

**Final decision: Scale launches at $2,999/mo with the tightened limits**. Margin: $224 (7%). Scale is a low-margin tier where we're paying for the customer relationship and case study. We expect Scale customers to upgrade to Enterprise within 12 months.

## Updated launch pricing

| Tier | Monthly | Annual (10mo discount) |
|---|---|---|
| Hobby | $19 | $190/yr |
| Solo Pro | $69 | $690/yr |
| Team | $499 | $4,990/yr |
| Scale | $2,999 | $29,990/yr |
| Enterprise | $5k–$25k+ custom | annual contract |

These are the numbers the dashboard, the marketing site, and the API server's quota table will use.

## Annual revenue projections

Year 1 conservative target customer counts (after 12 months of launch):

| Tier | Customers | MRR | Gross margin (at avg 50% utilization) |
|---|---|---|---|
| Hobby | 200 | $3,800 | $1,800 |
| Solo Pro | 80 | $5,520 | $1,500 |
| Team | 15 | $7,485 | $2,300 |
| Scale | 3 | $8,997 | $700 |
| Enterprise | 1 | $10,000 | $4,000 |
| **Total** | **299** | **$35,802 MRR** | **$10,300/mo** |

ARR Year 1: **$429k**, gross profit **$124k/year**.

Year 2 target with retention and conversion:

| Tier | Customers | MRR |
|---|---|---|
| Hobby | 600 | $11,400 |
| Solo Pro | 300 | $20,700 |
| Team | 80 | $39,920 |
| Scale | 20 | $59,980 |
| Enterprise | 8 | $80,000 |
| **Total** | **1,008** | **$212,000 MRR** |

ARR Year 2: **$2.5M**, gross profit ~$900k/year.

These numbers are what the financial section in [14-roadmap-and-finances.md](./14-roadmap-and-finances.md) builds the hiring plan against.

## What we explicitly do not charge for

- API key creation, rotation, or deletion.
- Dashboard usage.
- Documentation, CLI, SDK downloads.
- Read-only audit log access (within retention window).
- Memory deletion.
- Tenant data export (one full export per quarter included).

## What gets charged at overage rate even on Enterprise

- Custom regions outside the contract's specified regions.
- Out-of-band data export beyond the included quarterly snapshot.
- LLM token bundles consumed beyond the contract.

## How prices change

- Existing customers are grandfathered into their signup tier for 12 months minimum.
- Increases are announced 30 days in advance via email and dashboard banner.
- Decreases (limit increases at same price) are applied immediately and announced as an upgrade.
- We never silently degrade a tier's limits.

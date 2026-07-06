# 14 — Roadmap and Finances

This document covers the build-and-ship sequence, hiring plan, and financial projections for Year 1 and Year 2.

## Decisions of record

1. **Bootstrap-funded.** No outside capital sought before Year 2. Personal savings + early revenue cover infra and one full-time founder salary.
2. **Hire engineer #2 when MRR > $25k.** Then engineer #3 when MRR > $80k.
3. **No marketing spend before $20k MRR.** Until then, growth comes from developer-direct outreach, Show HN, dev community.
4. **Closed beta of 50 customers before public launch.** Calibrate pricing, support, retention before opening signups.
5. **Public launch only when retention is verified at 6 weeks for 80% of beta customers.**

## 12-week build plan (Sprint 1 → Sprint 12)

Each sprint is one week. The plan compresses the gaps identified in the repo audit into shippable increments.

### Sprint 1 — Foundation
- Replace demo auth with NextAuth + Postgres-backed accounts.
- Persist API keys in Postgres, replace `key_store` in-memory dict.
- Add `/healthz`, `/readyz`, `/metrics` routes.
- Add CORS, GZip, structured logging, request ID middleware.
- Wire `app.on_event("startup")` boot checks.
- Single image multi-mode entrypoint (api / worker / beat / migrate).
- **Demo at end of week**: `docker compose up` and the dashboard signs in against real auth.

### Sprint 2 — Pipeline end-to-end
- Wire extraction → dedup → entity-resolve → truth → score → store → embed in Celery chain.
- Implement `embedding_tasks.py` actual work.
- Implement `decay_tasks.py`, `reflection_tasks.py`, `dream_tasks.py` to call existing engines.
- Wire `/v1/retrieve` to call `RetrievalEngine` with real repos.
- Wire `/v1/memories/{id}/*` to call `MemoryLifecycleEngine`.
- Wire `/v1/sessions/*`.
- **Demo at end of week**: full observation → retrieval works against a real Postgres.

### Sprint 3 — Go data plane (Phase 1)
- Bootstrap `services/data-plane/` with chi + pgx + sqlc.
- Implement `/v1/observations` (POST), `/v1/observations/batch`.
- Port sensitive_filter to Go with shared catalog.
- Bench at 5k RPS observation ingest.
- **Demo at end of week**: ingest path lives in Go; Python still owns the rest.

### Sprint 4 — Go data plane (Phase 2)
- Implement `/v1/retrieve` in Go using the canonical hybrid SQL.
- Implement `/v1/memories/{id}` GET in Go.
- Implement `/v1/memories/{id}/{action}` POST in Go for lifecycle.
- Implement `/v1/context` in Go (calls retrieval + ContextBuilder logic ported in Go).
- Bench at 5k RPS retrieval, p95 < 100 ms.
- **Demo at end of week**: hot path lives in Go; latency p95 cut from 300 ms to ~70 ms.

### Sprint 5 — Edge gateway
- Bootstrap `services/gateway/` with chi.
- API key verification + LRU cache.
- Per-key Redis token bucket rate limiting.
- Per-tenant quota check.
- Internal header decoration.
- Routing rules.
- Per-request meter event emission.
- **Demo at end of week**: gateway in front, all upstreams behind it.

### Sprint 6 — Metering pipeline
- `usage_event`, `usage_daily`, `usage_period` tables + monthly partitions.
- Aggregator service in Go with leader election.
- `/v1/usage` endpoint.
- Stripe products and prices created via script.
- Stripe webhook handler.
- Stripe Customer Portal integration.
- **Demo at end of week**: end-to-end charge from observation → meter → period → Stripe usage record.

### Sprint 7 — Dashboard rebuild
- Rip out static mocks in `web/src/lib/data.ts`.
- Wire all dashboard pages to real API calls.
- Add shadcn/ui components.
- Implement projects list and detail pages.
- Implement billing page with Stripe Checkout/Portal.
- Implement usage page with charts (Recharts).
- Implement memory inspector with side drawer.
- **Demo at end of week**: a real customer flow from sign-up → first key → first observation → see usage.

### Sprint 8 — Pip SDK + CLI
- `clients/python/contexta_client/` package.
- Sync + async clients.
- Exhaustive method coverage (all endpoints in [04-api-contract.md](./04-api-contract.md)).
- CLI commands: login, init, test, projects, keys, policies, schemas, memories, observations, context, usage.
- Publish to PyPI under `contexta-client`.
- **Demo at end of week**: `pip install contexta-client && contexta test` works against staging.

### Sprint 9 — npm SDK + OpenAI Assistants integration
- `clients/typescript/` package.
- Equivalent surface to Pip SDK.
- `@contexta/openai` adapter.
- Publish to npm.
- **Demo at end of week**: a working OpenAI Assistants demo agent that uses contexta.

### Sprint 10 — LlamaIndex integration + docs site
- `contexta-llamaindex` adapter.
- Mintlify docs site at `docs.contexta.dev`.
- Pages: quickstart, concepts (observations, memories, importance, decay, reflection, dream), guides (OpenAI, LlamaIndex, custom loop), API reference (auto-generated from FastAPI), recipes (3 built-in policy templates).
- **Demo at end of week**: docs site is launchable; we pick 5 friendly devs to test.

### Sprint 11 — Anthropic + LangChain + Vercel AI integrations
- `contexta-anthropic`, `contexta-langchain`, `@contexta/vercel-ai`.
- Examples folder with 4 runnable agents.
- **Demo at end of week**: all 5 launch-day integrations published.

### Sprint 12 — Closed beta launch
- Onboard 50 beta customers, paying.
- Daily retention monitoring.
- Daily customer feedback loop.
- 1-on-1 onboarding calls for first 20 customers.
- Postmark + Resend transactional email going.
- Status page live.
- **End of week**: closed beta running with paying customers.

## Months 4–6 (post-launch)

| Sprint | Focus |
|---|---|
| 13–14 | Scale tier features: SSO (Google, GitHub), per-key audit access |
| 15 | Reliability hardening based on beta feedback |
| 16 | US edge gateway in `us-east-1` |
| 17–18 | Public launch (Show HN, ProductHunt, dev podcasts) |
| 19–20 | First $10k MRR |
| 21–24 | Hire engineer #2; SOC 2 Type I auditor engaged |

## Year 1 financial projection

### Conservative case

| Quarter | Customers (paying) | MRR | Cumulative Revenue | Infra | Founder salary | Other (Stripe, email, monitoring) | Net |
|---|---|---|---|---|---|---|---|
| Q1 (Sprints 1–12) | 0 | $0 | $0 | $1,800 ($600/mo × 3) | $24,000 | $300 | -$26,100 |
| Q2 | 50 paying ramp | $4,500 ramp | $7,000 | $1,800 | $24,000 | $400 | -$19,200 |
| Q3 | 150 | $12,000 ramp avg | $33,000 | $2,000 | $24,000 | $600 | -$26,000 (cumulative -$45,200) |
| Q4 | 300 | $25,000 avg | $75,000 | $2,400 | $24,000 | $1,000 | $48,000 (cumulative ~$2,800) |

End of Year 1: roughly cash-neutral. ~300 paying customers, $25-35k MRR. Founder paid through the year. Infra bills paid.

### Aggressive case (if launch goes well + a content piece goes viral)

| Quarter | Customers | MRR | Cumulative Revenue | Net |
|---|---|---|---|---|
| Q1 | 0 | $0 | $0 | -$26,100 |
| Q2 | 100 | $9k | $14k | -$12,100 (cumulative -$38,200) |
| Q3 | 350 | $28k | $76k | $50k (cumulative +$11,800) |
| Q4 | 700 | $58k | $174k | $146k (cumulative +$157,800) |

End of Year 1: $58k MRR, ~700 customers. Hire engineer #2 in Q3 (~$10k/mo ramping).

### Conservative cumulative ARR vs Series A milestone

A typical Series A in dev infra wants $1M ARR. Conservative case: end of Year 1 ARR is ~$300k-$420k. We're not at Series A bar.

That's fine. Plan is bootstrap to ~$1M ARR by Month 24 then optionally raise.

## Hiring plan

| Trigger | Hire | Why |
|---|---|---|
| Day 1 | Founder (full-time) | Engineering, product, support |
| MRR > $20k | Engineer #2 (Python + Go) | Burnout prevention; on-call rotation; ship faster |
| MRR > $50k | DevRel / Customer success #1 | Scale support to 100+ customers |
| MRR > $80k | Engineer #3 (full-stack TypeScript) | Dashboard + SDK + integrations parallelism |
| MRR > $150k | Engineer #4 (SRE) | Move to k8s, on-call coverage 24×5 |
| MRR > $300k | Designer + first salesperson | Move from PLG to PLS hybrid |

## Cost breakdown by month at MRR milestones

### Month 6 ($25k MRR, 250 customers, founder solo)

| Line | Cost |
|---|---|
| Founder salary | $8,000/mo |
| Infra (Hetzner + Cloudflare + Stripe + Postmark + Honeycomb) | $700/mo |
| Software (GitHub, Linear, Notion, etc.) | $200/mo |
| Domain/SSL/legal/accounting | $300/mo |
| **Total** | **$9,200/mo** |
| **Net margin** | **$15,800/mo (63%)** |

### Month 12 ($60k MRR, 700 customers, 2 engineers)

| Line | Cost |
|---|---|
| Founder | $10,000/mo |
| Engineer #2 | $8,500/mo |
| Infra | $1,500/mo |
| Software | $400/mo |
| Misc (legal, accounting, conferences) | $1,000/mo |
| **Total** | **$21,400/mo** |
| **Net margin** | **$38,600/mo (64%)** |

### Month 24 ($200k MRR, 2,000 customers, 5 people)

| Line | Cost |
|---|---|
| Salaries × 5 | $55,000/mo |
| Infra | $5,000/mo |
| Software | $1,500/mo |
| Sales tools, marketing tests | $4,000/mo |
| SOC 2 audit, security tooling | $3,500/mo |
| Misc | $3,000/mo |
| **Total** | **$72,000/mo** |
| **Net margin** | **$128,000/mo (64%)** |

64% gross margin is healthy for B2B dev infra and lines up with comparable companies (Vercel pre-IPO ~70%, Supabase 65–70%).

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| OpenAI API price spike | BYOK insulates us from 95% of LLM cost. Margin protected. |
| Mem0 / Letta / Zep get aggressive on pricing | Closed source means we ship features without forcing customers to upgrade. Differentiation on reflection + dream + truth maintenance. |
| Hetzner availability incident | EU dual-region. AWS US edge as separate provider. |
| Founder burnout | Hiring trigger at $20k MRR is aggressive on purpose. |
| Slow customer growth | At end of Q2, if MRR < $5k, switch from PLG to founder-led outbound for Q3. |
| Critical security incident at launch | Pre-launch external pentest mandatory before opening signups. |
| Compliance demand from one Enterprise prospect | Defer until Series A or hire dedicated compliance contractor. |

## Decision checkpoints

These are pre-committed go/no-go gates. We do not improvise around them.

| Month | Question | Decision |
|---|---|---|
| 3 (end of Sprint 12) | Is closed beta live with 50 paying? If not, freeze launch and review. |
| 6 | Is MRR > $20k? If yes, hire engineer #2. If no, focus on retention and conversion. |
| 9 | Is MRR > $40k? If yes, start SOC 2 process. If no, postpone. |
| 12 | Is ARR > $400k and growing > 10%/month? If yes, prepare optional Series A. If no, double down on PLG and conservative growth. |
| 18 | Is ARR > $1M? If yes, decide on Series A. |
| 24 | Is ARR > $2M? If yes, hire VP Eng + first AE. |

## What we will not do

- Take pre-revenue funding. The first dollar in is from a paying customer.
- Sell consulting alongside the product. We are a product company.
- Add a free tier before $1M ARR (locks in our identity as paid-quality service).
- Ship features that don't map to a customer's stated workflow.
- Promise SLAs we haven't proven. Public 99.9% uptime promise only ships at month 6 after sustained measurement.
- Open source any part of the engine, ever.


## What's explicitly NOT in MVP

The roadmap above ships the **frozen MVP scope**: SDK-first, observe + retrieve + context + explain + lifecycle, with extraction + classification + entity graph + clustering + importance + decay + hybrid retrieval. These are the pieces that prove PMF.

The following are designed and (partially) implemented in the codebase but are **deferred to post-PMF**:

| Capability | Status | Ships when |
|---|---|---|
| Reflection engine (autonomous nightly maintenance) | Code exists in `contexta/core/reflection/` | Phase B, after closed beta retention proven |
| Dream cycle (synthetic Q&A self-eval) | Code exists in `contexta/core/dream/` | Phase B |
| Memory compression beyond entity-scope | Code exists | Phase B |
| Hierarchical clustering | — | Phase B |
| Multimodal observations (image, audio, video) | — | Phase C |
| Agent simulation / self-learning loops | — | Phase C |
| Real-time WebSocket retrieval | — | Indefinite (no clear demand) |
| GraphQL API | — | Indefinite |
| Self-hosted production deployment for customers | — | Never (closed source forever) |

**Why this discipline matters:** the existing codebase is feature-rich enough that we could ship reflection and dream on day 1. We don't, because shipping more surface area to validate slows down PMF discovery. Customers will ask for the autonomous features once they're using the basic memory layer in anger; that's the right time to flip them on.

The closed beta success criteria (in the decision checkpoints above) explicitly include "is retention strong without reflection/dream?" If yes, those features become accelerants for Phase B. If retention is weak even with the basic memory layer, no amount of autonomous magic on top will save it.
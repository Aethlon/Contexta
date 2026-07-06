# contexta Business Plan

This folder is the operating manual for the contexta product, infrastructure, and business. Every document here is the source of truth for how the company runs the engine, prices it, builds it, and ships it.

The audience is internal: founders, engineers, and the first hires. Every doc is written so a new engineer can read it cold and ship correct work without asking questions.

## What contexta is

contexta is a closed-source, hosted memory intelligence layer for AI agents. Customers send conversation observations, contexta extracts structured memories, scores them, stores them in a hybrid index, and serves contextually relevant memories back to the agent on demand. The product covers the full lifecycle: observation, extraction, classification, contradiction resolution, scoring, storage, retrieval, decay, reflection, and self-evaluation.

The codebase has three top-level surfaces:

- `contexta/` — the Python backend engine, served as a FastAPI service plus Celery workers.
- `web/` — the Next.js dashboard for accounts, API keys, billing, projects, and docs.
- `Business plan/` — this folder.

Future surfaces (planned, not yet in repo):

- `clients/python/` — Pip SDK and CLI.
- `clients/typescript/` — npm SDK.
- `services/data-plane/` — Go service for hot read/write paths.
- `services/edge-gateway/` — Go service for rate limiting, auth verification, request fan-out.

## Document index

| # | Document | What it covers |
|---|---|---|
| 00 | [vision-and-positioning.md](./00-vision-and-positioning.md) | Who we sell to, what we are, what we are not, the wedge |
| 01 | [pricing-and-unit-economics.md](./01-pricing-and-unit-economics.md) | Tiers, dimensions, cost math, profit per tenant |
| 02 | [architecture-overview.md](./02-architecture-overview.md) | Polyglot stack, dedicated machines, traffic flow |
| 03 | [backend-runtime.md](./03-backend-runtime.md) | How `contexta/` runs in production, single-image multi-mode |
| 04 | [api-contract.md](./04-api-contract.md) | Internal wire contract, read vs write classification, scopes, errors |
| 05 | [database-strategy.md](./05-database-strategy.md) | Self-hosted Postgres + pgvector, tiered storage, replication |
| 06 | [polyglot-services.md](./06-polyglot-services.md) | Go data plane + edge gateway, contracts with Python |
| 07 | [metering-and-billing.md](./07-metering-and-billing.md) | Usage events, aggregation, Stripe, hooks, accuracy guarantees |
| 08 | [web-backend-integration.md](./08-web-backend-integration.md) | Auth, sessions, dashboard ↔ API wiring, key rotation |
| 09 | [dashboard-spec.md](./09-dashboard-spec.md) | Tabs, screens, wireframe-level UI spec |
| 10 | [integrations.md](./10-integrations.md) | OpenAI Assistants, LlamaIndex, Anthropic, LangChain, custom loops |
| 11 | [cli-and-sdk.md](./11-cli-and-sdk.md) | Pip + npm packaging, CLI command surface |
| 12 | [deployment-topology.md](./12-deployment-topology.md) | Dedicated machines, network layout, dataflow, region plan |
| 13 | [operations-and-security.md](./13-operations-and-security.md) | Healthz, metrics, logging, auth, audit, incident response |
| 14 | [roadmap-and-finances.md](./14-roadmap-and-finances.md) | 12-week build plan, revenue projections, hiring plan |
| 15 | [retrieval-deep-dive.md](./15-retrieval-deep-dive.md) | Four-stage retrieval pipeline, accuracy/latency targets |
| 16 | [error-handling-and-failsafe.md](./16-error-handling-and-failsafe.md) | Idempotency, durable buffer, replay, every failure mode |
| 17 | [security-and-abuse-protection.md](./17-security-and-abuse-protection.md) | DB spam protection, tenant isolation hardening, threat model |
| 18 | [sdk-first-product-contract.md](./18-sdk-first-product-contract.md) | The SDK as the public product, twelve methods, internals |
| 19 | [edge-cases-and-data-integrity.md](./19-edge-cases-and-data-integrity.md) | Every edge case with defined behavior |

## How to use these docs

- Read 00, 01, 02 first if you want the business and architecture overview in 20 minutes.
- Read 03, 04, 05, 06 if you are building the backend.
- Read 08, 09 if you are building the web dashboard.
- Read 10, 11 if you are building developer-facing surfaces.
- Read 07, 12, 13 if you are running the production environment.
- Read 14 if you are planning hiring or fundraising.

## Decisions of record

These decisions are final unless explicitly revisited. Every doc in this folder follows them.

1. **Closed source forever.** No GitHub mirror. No tarball downloads. No "self host the engine yourself" tier. Customers run their agents locally, but the memory layer always runs on contexta infrastructure.
2. **SDK-first.** The Pip and npm SDKs are the public product. The HTTP API is the wire contract underneath; documented but not the headline.
3. **Frozen MVP scope: phase 1 + phase 2 merged.** Day-1 ship: extraction, classification, entity resolution, relationship graph, clustering, importance scoring, decay, hybrid retrieval, explainability. Reflection, dream cycle, and autonomous maintenance ship post-PMF.
4. **BYOK by default.** Customers bring their own OpenAI/Anthropic API key for LLM calls. Managed-LLM is an opt-in paid add-on with markup.
5. **Self-hosted infrastructure.** Postgres, Redis, and the application services run on contexta-controlled servers (Hetzner dedicated to start, multi-region later). No managed Postgres dependency for the hot path.
6. **Polyglot stack.** Python for AI/LLM/extraction, Go for hot data plane and edge gateway. No Rust until a real bottleneck demands it.
7. **One shared multi-tenant database.** Shared cluster with `organization_id` row keys. No per-user DBs, no per-tenant schemas. Sharding deferred until ~30M active memories tenant-wide.
8. **Active developer relationship.** Every paying customer has a direct Slack/Discord channel with the team. Feedback ships within one week unless infra-blocked. Pricing tiers are generous on cost so customers grow with us.
9. **Free tier later, not now.** Paid only at launch. Free tier gates open after Series A or 1k paying customers, whichever comes first.

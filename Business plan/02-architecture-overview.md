# 02 — Architecture Overview

This is the 30,000-foot architecture. Detailed runtime, database, and polyglot service docs follow in 03, 05, 06.

## Decisions of record

1. **Self-hosted dedicated infrastructure.** Hetzner dedicated boxes in Germany (FSN1) and Finland (HEL1) for v1. AWS/GCP only for edge gateway in regions where Hetzner doesn't cover. This is a 4–5x cost reduction vs cloud-managed equivalents, which is what makes the unit economics work.
2. **Polyglot stack: Python + Go.**
   - **Python**: AI/LLM/extraction/scoring/reflection/dream/clustering. Python's mature SDK ecosystem (OpenAI, Anthropic, LlamaIndex) is the reason. CPU is not the bottleneck here; LLM latency is.
   - **Go**: Edge gateway, data plane (hot read/write paths), metering aggregator, rate limiter. Go's concurrency, GC profile, and binary distribution beat Python at IO-bound fan-out. We get >50k RPS on a single Go gateway instance vs ~3k RPS for FastAPI.
   - **No Rust at v1.** Rust is reserved for one specific case: a token-counting library bundled into the SDK. Even that can wait. C++ is never used.
3. **Each tier of compute lives on its own machine class.**
   - Edge gateway: small CPU-optimized VMs.
   - API tier (Python): medium memory-optimized.
   - Worker tier (Python + LLM): scales by queue depth.
   - Data plane (Go): close to Postgres, large NIC.
   - Postgres+pgvector: dedicated bare-metal with NVMe.
   - Redis: small dedicated VM, replicated.
4. **Single Docker image, multiple modes.** The Python `contexta` image runs as `api`, `worker`, `beat`, or `migrate` based on `CMD`. The Go services have their own slim images.
5. **Async write path, sync read path.** Writes (observations) return 202 in <50ms; processing happens in workers. Reads (retrieval, context) are synchronous and target p95 < 200ms.

## High-level traffic flow

```
                ┌───────────────────────────────┐
   Customer →   │ Edge Gateway (Go)             │   Stateless, horizontal
   agent SDK    │  - TLS termination            │   ~$10/mo per instance
                │  - API key verify (cached)    │   Target: 50k RPS / instance
                │  - Per-key rate limit         │
                │  - Quota check (cached)       │
                │  - Meter event emit           │
                │  - Route by tenant            │
                └────────────┬──────────────────┘
                             │
                ┌────────────▼──────────────────┐
                │ Data Plane (Go)               │   Hot read/write
                │  - /observations  (write)     │   - Direct Postgres pool
                │  - /retrieve      (read)      │   - Hybrid SQL retrieval
                │  - /memories/*    (read/lifecycle) - Redis Hot Context
                │  - /context       (read)      │   - Sub-50ms p99 reads
                └─────┬──────────────┬──────────┘
                      │              │
                writes│              │ reads
                      │              │
        ┌─────────────▼───┐    ┌─────▼─────────────┐
        │ Redis           │    │ Postgres + pgvector
        │  - streams      │    │  - HOT shard (HNSW, RAM-pinned)
        │  - hot context  │    │  - WARM shard (HNSW, smaller RAM)
        │  - rate limit   │    │  - COLD shard (IVFFlat, on disk)
        │  - meter buffer │    │  - Read replicas (HOT only)
        └─────┬───────────┘    └────▲──────────────┘
              │ pull                 │ persist
              │                      │
        ┌─────▼──────────────────────┴──────────┐
        │ API Tier (Python / FastAPI)            │   Slow control plane
        │  - /api-keys, /sessions, /policy/*     │   ~3k RPS / instance
        │  - /schemas, /admin/*                  │
        │  - explain, timeline                   │
        └──────────────┬────────────────────────┘
                       │
        ┌──────────────▼────────────────────────┐
        │ Worker Tier (Python / Celery)         │   Scale on queue depth
        │  ┌──────────────┐ ┌────────────────┐  │   KEDA-driven autoscale
        │  │ extraction   │ │ embedding      │  │
        │  │ (LLM)        │ │ (OpenAI)       │  │
        │  └──────────────┘ └────────────────┘  │
        │  ┌──────────────┐ ┌────────────────┐  │
        │  │ rerank       │ │ maintenance    │  │   Spot/preemptible OK
        │  │ (LLM, opt)   │ │ (decay, dream) │  │   for maintenance
        │  └──────────────┘ └────────────────┘  │
        └────────────────────────────────────────┘
                       │
        ┌──────────────▼────────────────────────┐
        │ Object Storage (S3 / Hetzner Storage) │
        │  - Archived tier (memories > 1yr)     │
        │  - Audit log archive                  │
        │  - Customer data exports              │
        └────────────────────────────────────────┘
```

## Why the data plane is in Go and not Python

This is the main architectural decision new engineers ask about. Reasoning:

- **Hot reads** (`/retrieve`, `/context`, `/memories/{id}`) make up ~95% of total request volume in production agent workloads. Each retrieval is mostly DB IO with a small amount of scoring math.
- FastAPI on a single instance benchmarks at ~3,000 req/s for trivial routes and ~600 req/s for routes that hit Postgres. Go with `pgx` benchmarks at ~50,000 req/s and ~12,000 req/s respectively.
- That's a ~20x difference in instances needed. At our pricing, that's the difference between the data plane costing $200/mo vs $4,000/mo.
- Python keeps the parts where the speedup matters less but the ecosystem matters more: extraction (LLM-bound, latency dominated by OpenAI), worker tasks (already async via Celery), reflection/dream (rare, batch).

The Go data plane reuses the **same Postgres database** as Python. There is no data sync. There is no separate ORM. The Go service uses raw SQL through `pgx` and is generated from the SQLAlchemy schema via `sqlc` (see doc 06).

## Why we don't use Rust at v1

We considered Rust for the data plane. We rejected it because:

- Rust libraries for Postgres (`tokio-postgres`, `sqlx`) and HTTP (`axum`) are mature but the team's velocity in Rust is ~30% of velocity in Go.
- The IO-bound nature of the workload means Rust's CPU advantage is invisible: 99% of latency is network round-trip to Postgres.
- Rust shines for CPU-bound work (compression, parsing, simulation). We don't have that hot path yet.

When we do hit a CPU-bound bottleneck (most likely: query embedding for inline retrieval), we will write that single component in Rust as a Python extension via PyO3. Not before.

## Where customer data lives

| Data | Storage | Encryption | Region |
|---|---|---|---|
| Memory records | Postgres (primary) | TLS in transit, AES-256 at rest (LUKS) | Customer's chosen region (FSN1/HEL1 v1) |
| Embeddings | Postgres pgvector column | Same as above | Same |
| Sessions, audit | Postgres | Same | Same |
| Hot context cache | Redis | TLS in transit, in-memory only | Same as Postgres |
| Archived memories | Hetzner Storage Box (S3-compat) | AES-256 at rest, customer-side keys for Enterprise | Same region |
| API keys | Postgres (hashed) | SHA-256 hash + 16-char prefix for display | Same |
| Customer billing data | Stripe (PCI scope) | Stripe-owned | US (Stripe's choice) |
| Session cookies (dashboard) | Customer browser | HttpOnly, SameSite=Lax, encrypted via NextAuth | N/A |

## What runs in which region (v1)

- **EU primary** (Hetzner FSN1, Falkenstein, Germany): default region for all customers at launch.
- **EU failover** (Hetzner HEL1, Helsinki, Finland): Postgres physical replica, Redis sentinel, warm standby for API/data plane.
- **US edge** (planned month 4): single edge gateway VM in `us-east-1` (AWS) for US customer latency, but data plane and DB still terminate in EU. Requests round-trip to FSN1.
- **US primary** (planned month 9, when MRR justifies): full data plane + DB in `us-east-1` (Hetzner doesn't cover US, so AWS Bare Metal or Vultr Bare Metal).
- **AP edge** (planned month 12): SG/Tokyo edge gateway only.

This means at launch, US customers will see ~120ms TLS handshake + ~40ms application latency. We will message this clearly. The dashboard region selector will gray out US-primary until it's available.

## Capacity and cost at launch

These numbers are for the first 6 months of operation, sized to handle 1,000 paying customers without resizing.

| Tier | Specification | Hetzner cost |
|---|---|---|
| Edge gateway × 2 | CCX13 (2 vCPU, 8 GB) | $20/mo |
| API × 3 | CCX23 (4 vCPU, 16 GB) | $90/mo |
| Data plane × 2 | CCX33 (8 vCPU, 32 GB) | $120/mo |
| Worker (always-on) × 2 | CCX23 | $60/mo |
| Worker (burst pool) | KEDA, scales 0–10 | ~$50/mo amortized |
| Postgres primary | AX52 (Ryzen 7 7700, 64 GB RAM, 2× NVMe) | $115/mo |
| Postgres replica | AX52 | $115/mo |
| Redis primary | CCX23 | $30/mo |
| Redis replica | CCX13 | $10/mo |
| S3 archive | Hetzner Storage Box 1TB | $5/mo |
| **Total dedicated infra** | | **~$615/mo** |

At Year 1 target MRR of $35k, that's a 1.7% infra cost ratio. Well within healthy SaaS margins.

## What ships in which sprint

The phasing in [14-roadmap-and-finances.md](./14-roadmap-and-finances.md) controls when each piece lands. As a quick reference:

| Sprint | Component | Status |
|---|---|---|
| Sprint 1 | API tier (Python), real auth, persisted API keys, healthz/metrics | Partially built |
| Sprint 2 | Worker pipeline end-to-end (extraction → store → embed) | Mostly built, persistence missing |
| Sprint 3 | Data plane (Go) for `/observations`, `/retrieve`, `/context`, `/memories/{id}` | Not started |
| Sprint 4 | Edge gateway (Go) with rate limit + quota | Not started |
| Sprint 5 | Metering pipeline + Stripe billing | Not started |
| Sprint 6 | Dashboard rebuild with real auth + tabs | Partially built |
| Sprint 7 | Pip SDK + CLI | Not started |
| Sprint 8 | npm SDK + OpenAI Assistants integration | Not started |
| Sprint 9 | LlamaIndex integration + docs site | Not started |
| Sprint 10 | Soft launch, first 50 paying customers | — |

**Reflection engine, dream cycle, compression, and advanced clustering are explicitly post-MVP.** They are designed and partially implemented in `contexta/core/` but not part of the v1 product. See [00-vision-and-positioning.md](./00-vision-and-positioning.md) for rationale.

## Key cross-cutting concerns

These appear in every doc and every component:

1. **Tenant isolation.** Every Postgres row has `organization_id`. Every Postgres query has a WHERE on it. Every Go handler reads tenant from JWT and scopes queries. Every Python repo extends `TenantScopedRepository`. No exceptions.
2. **Idempotency.** Writes accept an `Idempotency-Key` header. The data plane stores keys in Redis with a 24-hour TTL. Replays return the original 202 response unchanged.
3. **Observability.** Every request has a `request_id` (W3C `traceparent`). Every log line includes `tenant_id`, `actor_id`, `request_id`, `endpoint`. OpenTelemetry traces flow through gateway → data plane → Postgres.
4. **Quota enforcement.** Pre-request: Redis lookup. Post-request: meter event. Aggregator rolls up hourly.
5. **Backwards compatibility.** API versioning by URL prefix (`/v1/...`). Breaking changes get a new prefix. Old prefix supported for 12 months minimum.

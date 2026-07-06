# 06 — Polyglot Services: Go Data Plane and Edge Gateway

This document covers the two Go services that complement the Python `contexta/` backend: the **edge gateway** and the **data plane**. They are why contexta can hit production-grade latency and concurrency without exploding infrastructure cost.

## Why Go and not extending Python

Python with FastAPI on a single CCX23 instance benchmarks at:

- ~3,000 RPS for in-memory routes.
- ~600 RPS for routes that hit Postgres (with asyncpg + connection pool).
- ~150 RPS for routes that hit Postgres with pgvector cosine search.

Go with `pgx` and `chi` on the same instance:

- ~50,000 RPS for in-memory routes.
- ~12,000 RPS for routes that hit Postgres.
- ~3,500 RPS for the same pgvector cosine search.

The gap is the runtime. Python's GIL and per-request memory allocation are dominant at high RPS. Go's goroutines + value semantics + GC tuned for low latency win this benchmark every time.

For the hot data plane (95% of customer request volume), this gap is the difference between needing 2 boxes vs 20 boxes. At our pricing structure, that's the difference between healthy margins and bleeding money.


## Service split

| Service | Language | Responsibility | Repo path |
|---|---|---|---|
| Edge gateway | Go | TLS terminate, auth verify, rate limit, quota check, meter emit, route | `services/gateway/` |
| Data plane | Go | Hot reads (`/retrieve`, `/context`, `/memories/{id}`), hot writes (`/observations`) | `services/data-plane/` |
| Control plane API | Python | Everything else (api-keys, projects, billing, policies, schemas, audit, explain, timeline) | `contexta/` |
| Workers | Python | Async extraction, embedding, decay, reflection, dream | `contexta/workers/` |

The split is by **endpoint criticality**, not by feature. The gateway handles every request. The data plane handles high-RPS endpoints. Python handles low-RPS endpoints and all batch work.

## Edge gateway

### What it does

```
Customer agent
     │
     ▼
[ TLS terminate (Caddy or built-in TLS) ]
     │
     ▼
[ Parse Authorization header ]
     │
     ▼
[ Look up API key in Redis cache (LRU 100k entries) ]
     │ (miss) ─→ [ Read from Postgres api_key table ] ─→ [ Cache ]
     ▼
[ Resolve tenant_id, scopes, project_id ]
     │
     ▼
[ Per-key token bucket rate limit (Redis INCR) ]
     │
     ▼
[ Per-tenant quota check (Redis read of monthly counter) ]
     │
     ▼
[ Match scope to endpoint requirement ]
     │
     ▼
[ Decorate request with internal headers ]
     │
     ▼
[ Route by path:
     /v1/observations, /v1/retrieve, /v1/memories/* ─→ data plane (Go)
     everything else                                ─→ Python API ]
     │
     ▼
[ On response: emit usage event to Redis Stream ]
     │
     ▼
[ Return to customer ]
```

### Auth verification

The gateway is the only place that touches API keys. It maintains an LRU cache of `(token_hash → ApiKey{tenant_id, scopes, project_id, status})` with 5-minute TTL.

```go
type ApiKey struct {
    ID            uuid.UUID
    TokenHash     string    // sha256
    TenantID      uuid.UUID
    ProjectID     uuid.UUID
    Scopes        []string
    Status        string    // "active" | "revoked" | "expired"
    LastUsedAt    time.Time
}

func (g *Gateway) verifyKey(ctx context.Context, bearer string) (*ApiKey, error) {
    hash := sha256Hex(bearer)
    if cached, ok := g.keyCache.Get(hash); ok {
        return cached, nil
    }
    key, err := g.repo.FindByHash(ctx, hash)
    if err != nil {
        return nil, ErrInvalidKey
    }
    if key.Status != "active" {
        return nil, ErrKeyRevoked
    }
    g.keyCache.Add(hash, key)
    return key, nil
}
```

`last_used_at` updates are batched: every 60 seconds the gateway flushes a Redis set of "keys touched recently" into a single `UPDATE api_key SET last_used_at = NOW() WHERE id = ANY($1)`. This avoids one Postgres write per request.


### Rate limiting

Per-key token bucket in Redis using the standard Lua script pattern (atomic INCR + EXPIRE):

```lua
-- KEYS[1]: bucket key, e.g., "rl:key:01J9ZX..."
-- ARGV[1]: capacity
-- ARGV[2]: refill_per_sec
-- ARGV[3]: now_ms
-- Returns: 1 if allowed, 0 if blocked, plus remaining tokens

local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local bucket = redis.call("HMGET", KEYS[1], "tokens", "last")
local tokens = tonumber(bucket[1]) or capacity
local last = tonumber(bucket[2]) or now

local elapsed_ms = math.max(0, now - last)
tokens = math.min(capacity, tokens + (elapsed_ms / 1000.0) * refill)

local allowed = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
end

redis.call("HMSET", KEYS[1], "tokens", tokens, "last", now)
redis.call("PEXPIRE", KEYS[1], 60000)
return {allowed, math.floor(tokens)}
```

Limits per tier (concurrent RPS cap from [01-pricing-and-unit-economics.md](./01-pricing-and-unit-economics.md)):

| Tier | RPS cap | Burst |
|---|---|---|
| Hobby | 10 | 20 |
| Solo Pro | 50 | 100 |
| Team | 250 | 500 |
| Scale | 1000 | 2000 |
| Enterprise | custom | custom |

When blocked: 429 with `Retry-After: <seconds>` header.

### Quota check

Pre-request lookup against a per-tenant monthly counter in Redis:

```
GET quota:obs:01J9ZX:2026-05  → 213400
```

If the counter is at or above the plan limit AND the tenant has hard cap enabled, return 429 `quota_exceeded`. Otherwise allow with a header `X-contexta-Quota-Used: 0.426`.

The counter is incremented post-request by the meter pipeline (see [07-metering-and-billing.md](./07-metering-and-billing.md)).

### Internal headers

After verification the gateway forwards to upstream with these headers:

```
X-Mem-Tenant-Id: 22222222-2222-4222-8222-222222222222
X-Mem-Actor-Id: 11111111-1111-4111-8111-111111111111
X-Mem-Key-Id: 01J9ZXAB1Q2R3S4T5V6W7X8Y9Z
X-Mem-Project-Id: 33333333-3333-4333-8333-333333333333
X-Mem-Scopes: observations:write,retrieval:read
X-Mem-Trace-Id: 01J9ZXAB1Q2R3S4T5V6W7X8Y9Z
X-Mem-Plan: solo-pro
```

Upstream services (Python API, Go data plane) trust these only when the connection comes from the internal VPC. The Caddy/ingress config drops all `X-Mem-*` headers from external traffic.

The internal trust boundary is enforced by:

1. Network: gateways and upstream services share a private VPC; gateway listens on public IP, upstreams on private IPs only.
2. mTLS: gateway → upstream connections use mutual TLS with cert pinning (in production phase 2).

### Routing rules

```yaml
# gateway routes (illustrative)
- path: "/v1/observations"
  upstream: data-plane
- path: "/v1/observations/batch"
  upstream: data-plane
- path: "/v1/retrieve"
  upstream: data-plane
- path: "/v1/context"
  upstream: data-plane
- path: "/v1/memories/{id}"
  methods: ["GET"]
  upstream: data-plane
- path: "/v1/memories/{id}/{action}"
  methods: ["POST", "DELETE"]
  upstream: data-plane    # lifecycle ops are simple, fast
- path: "/v1/memories/{id}/explain"
  upstream: python-api    # joins audit + version tables, low-RPS
- path: "/v1/memories/timeline/{user_id}"
  upstream: python-api
- path: "/v1/sessions/*"
  upstream: data-plane    # session writes are fast
- path: "/v1/policies/*"
  upstream: python-api
- path: "/v1/schemas/*"
  upstream: python-api
- path: "/v1/keys/*"
  upstream: python-api
- path: "/v1/usage*"
  upstream: python-api
- path: "/v1/audit*"
  upstream: python-api
- path: "/v1/billing/*"
  upstream: python-api
- path: "/v1/projects*"
  upstream: python-api
- path: "/healthz"
  handler: gateway-self
- path: "/readyz"
  handler: gateway-self
- path: "/metrics"
  handler: gateway-self
```


## Data plane

### Responsibility

Owns the four endpoint families that have the highest RPS:

1. `POST /v1/observations` and `/batch` — ingest, redact, enqueue.
2. `POST /v1/retrieve` — hybrid SQL retrieval.
3. `GET /v1/context` — retrieval + context bundle assembly.
4. `GET /v1/memories/{id}` and lifecycle ops (pin/unpin/archive/restore/delete).

These are the calls an agent makes once per turn at minimum. A heavy agent makes 5+ retrieval calls per turn.

### Architecture

```go
// services/data-plane/internal/server/server.go
type Server struct {
    db          *pgxpool.Pool
    redis       *redis.Client
    extractTopic string                  // Redis Stream key for handoff to Python workers
    sensitive   *redaction.Filter        // Go port of sensitive_filter.py
    meter       *metering.Emitter
    logger      *slog.Logger
    tracer      trace.Tracer
}
```

### Sensitive data redaction (port to Go)

The Python `sensitive_filter.py` is well-specified and worth reusing. We port its regex catalog to Go and freeze it as a versioned spec. Both implementations are tested against the same fixture file.

Why port instead of calling Python? Because every observation goes through the data plane first, and the regex pass is on the hot path. ~50µs in Go vs ~1.2ms across an HTTP hop to Python.

```go
// services/data-plane/internal/redaction/filter.go
package redaction

type Pattern struct {
    Name  string
    Regex *regexp.Regexp
    Mode  RedactionMode  // Replace, ReplaceCapture, ReplaceLuhn
}

var patterns = []Pattern{
    {Name: "password", Regex: regexp.MustCompile(`(?i)(password|passwd|pwd)\s*[=:]\s*["']?([^\s"',;}{)\]]+)["']?`), Mode: ReplaceCapture},
    {Name: "openai_key", Regex: regexp.MustCompile(`\b(sk-[A-Za-z0-9]{20,})\b`), Mode: Replace},
    // ...full catalog from sensitive_filter.py
}
```

The catalog is regenerated from a shared `redaction-catalog.yaml` checked into the repo. CI tests both Python and Go ports against the same fixtures.

### Observation ingest path (Go)

```
1. Receive POST /v1/observations
2. Read X-Mem-Tenant-Id, X-Mem-Actor-Id from internal headers (already verified by gateway)
3. Validate body shape (basic JSON, size, required fields)
4. Run redaction pass on serialized messages
5. Write a small "observation" row to Postgres (just metadata, not full body)
6. XADD payload + observation_id to Redis Stream "extraction:queue"
7. Emit meter event "observation_accepted" with bytes, message count
8. Return 202 with job_id (= observation_id)
```

Python extraction worker XREADGROUP from the same stream, processes, and writes the resulting memories back to Postgres. This decouples the Go fast path from the slow LLM extraction.

### Retrieval path (Go)

This is the canonical hot path:

```go
func (s *Server) Retrieve(ctx context.Context, req *RetrieveRequest) (*RetrieveResponse, error) {
    ctx, span := s.tracer.Start(ctx, "retrieve")
    defer span.End()

    tenantID := tenantFromContext(ctx)
    userID   := req.UserID

    // 1. Compute query embedding (parallel with keyword tokenization)
    embChan := make(chan []float32, 1)
    go func() {
        emb, _ := s.embedClient.Embed(ctx, req.QueryText)
        embChan <- emb
    }()

    // 2. Resolve seed entities (entity-aware retrieval)
    seedEntities, _ := s.resolveSeedEntities(ctx, tenantID, userID, req.QueryText)

    queryEmb := <-embChan

    // 3. Run the canonical hybrid query (see 05-database-strategy.md)
    rows, err := s.db.Query(ctx, hybridRetrieveSQL,
        queryEmb,
        tenantID,
        userID,
        req.MemoryTypes,
        req.Tags,
        req.QueryText,
        seedEntities,
        req.Limit,
    )
    if err != nil {
        return nil, err
    }
    defer rows.Close()

    // 4. Materialize results
    results := []ScoredMemory{}
    for rows.Next() {
        var m ScoredMemory
        if err := rows.Scan(&m.ID, &m.Title, &m.Content, &m.Score, /* ... */); err != nil {
            return nil, err
        }
        results = append(results, m)
    }

    // 5. Optional rerank
    if req.Rerank {
        results, err = s.rerank.Rerank(ctx, req.QueryText, results)
        if err != nil {
            // graceful: log and return non-reranked results
            s.logger.Warn("rerank failed", "err", err)
        }
    }

    // 6. Emit meter event
    s.meter.Emit(ctx, MeterEvent{
        Type: "retrieval",
        Reranked: req.Rerank,
        ResultCount: len(results),
    })

    return &RetrieveResponse{Results: results, ElapsedMs: timeSince(ctx)}, nil
}
```

### Why not call the Python `RetrievalEngine` from Go via HTTP?

Tested. Adding an HTTP hop to Python adds ~8 ms p50 and ~30 ms p99 of overhead. That doubles our retrieval latency budget. Owning the SQL in Go saves the hop entirely.

The Python `RetrievalEngine` continues to exist for the Python control plane (`/explain` uses it indirectly to fetch memories) and as the reference implementation for tests.

### sqlc for type-safe queries

We generate Go types and methods from the SQL schema using [sqlc](https://sqlc.dev/):

```yaml
# services/data-plane/sqlc.yaml
version: "2"
sql:
  - engine: postgresql
    queries: ./internal/storage/queries/
    schema: ../../contexta/migrations/versions/
    gen:
      go:
        package: storage
        out: ./internal/storage/sqlc
        sql_package: pgx/v5
        emit_pointers_for_null_types: true
        overrides:
          - column: "memory_record.embedding"
            go_type:
              import: github.com/pgvector/pgvector-go
              type: Vector
```

CI runs `sqlc generate` and fails if the queries are out of sync with the schema. Schema is owned by Python's Alembic; Go is read-only on the schema definition.

## Build and deploy

Each Go service has its own slim Dockerfile:

```dockerfile
# services/gateway/Dockerfile
FROM golang:1.23-alpine AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . ./
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /out/gateway ./cmd/gateway

FROM gcr.io/distroless/static:nonroot
COPY --from=builder /out/gateway /gateway
EXPOSE 443 8080
ENTRYPOINT ["/gateway"]
```

Image size: ~12 MB. Boot time: <100ms. Memory: ~30 MB idle, scales linearly.

## Testing strategy

| Layer | Tool | Coverage target |
|---|---|---|
| Unit | `go test`, `testify` | 80% |
| Property | `quick.Check` for redaction parity with Python | 100% of catalog |
| Integration | `testcontainers-go` with Postgres + Redis | full hot path |
| Load | `vegeta` against staging | 5k RPS sustained for 10 minutes |

A nightly job runs the redaction catalog against both Python and Go ports with the same 100k-fixture corpus and fails if any drift detected.


## No Python hop on the retrieval path

This is worth restating because it's the single most-impactful architectural choice:

**The retrieval call path is: SDK → Cloudflare → Go gateway → Go data plane → Postgres.**

There is no Python in the customer-perceived retrieval latency. Python's `RetrievalEngine` exists as the reference implementation and powers `/v1/memories/{id}/explain` (low-RPS, joins audit + version data). It does not power `/v1/retrieve` or `/v1/context` in production.

Adding Python to the retrieval path was tested. Findings:
- HTTP hop adds ~8 ms p50 and ~30 ms p99.
- Python's GIL contention adds ~5 ms p99 under load.
- Memory allocator pressure increases tail latency.
- Total Python-included p99 was ~150 ms vs ~80 ms Go-only.

That's a 2x latency degradation for zero functional benefit. The Go data plane reads from the same Postgres database with the same SQL.

The Go data plane stays read-mostly. Writes to memories happen in two places:
- The data plane writes the `observation_envelope` row (the durable receipt).
- Python workers, after extraction, write the actual memory rows.

This split keeps Python out of the latency-sensitive read path while keeping it on the LLM-bound write path where its ecosystem matters.

## Code generation contract

Both Python and Go services depend on the same Postgres schema. We use:

- **Schema source of truth:** Alembic migrations in `contexta/migrations/`, owned by Python.
- **Python ORM:** SQLAlchemy 2.0, mapped from migrations.
- **Go queries:** `sqlc` generates type-safe Go from raw SQL queries against the same schema.

CI runs `sqlc generate` and fails if Go's generated types don't match the latest migration. This catches schema drift between languages.

The Go data plane never runs migrations. Python's migrate job is the only writer of DDL.

## Service boundaries summary

| Concern | Owner | Language |
|---|---|---|
| Schema migrations | Python | Alembic |
| Memory extraction (LLM) | Python worker | Python |
| Embedding generation | Python worker | Python |
| Truth maintenance | Python worker | Python |
| Reflection / dream / compression (post-MVP) | Python worker | Python |
| Hot path: observation ingest | Go data plane | Go |
| Hot path: retrieval | Go data plane | Go |
| Hot path: context | Go data plane | Go |
| Hot path: lifecycle ops | Go data plane | Go |
| Auth verify, rate limit, quota, meter | Go gateway | Go |
| Sensitive data redaction | Both, via shared YAML catalog | Go (gateway), Python (worker secondary) |
| API key CRUD, projects, billing, audit, explain, timeline | Python API | Python |
| Aggregator (usage events → Postgres) | Aggregator service | Go |

This split is final unless we hit a hot path that demands Python (we won't) or a control-plane endpoint that demands Go (we won't).
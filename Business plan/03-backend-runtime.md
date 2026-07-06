# 03 — Backend Runtime: How `contexta/` Runs in Production

This document explains, line by line, what happens when you boot the `contexta/` Python backend in production. It is the answer to "if I run the contexta folder on my server, will it just work?"

Today the answer is: not quite. This doc specifies the changes needed to make it true, then how it should run.

## What the `contexta/` folder is

`contexta/` is a Python package, not a service. To turn it into a running service we need four processes plus two stateful dependencies:

| Process | Command | Purpose |
|---|---|---|
| API | `uvicorn contexta.api.app:app --host 0.0.0.0 --port 8000` | HTTP control plane, observations, sessions, api-keys |
| Worker | `celery -A contexta.workers.celery_app.celery_app worker --queues extraction,embedding,maintenance` | Async task processing |
| Beat | `celery -A contexta.workers.celery_app.celery_app beat` | Periodic schedule trigger (decay, reflection, dream) |
| Migrate | `alembic upgrade head` | One-shot at boot, behind an advisory lock |
| Postgres | external dependency (see [05-database-strategy.md](./05-database-strategy.md)) | Storage |
| Redis | external dependency | Queue + cache |

In production we want **one Docker image** that can run any of these modes via `CMD`. That keeps the build, scan, sign, and deploy pipeline simple.

## The single image

We replace the existing `Dockerfile` with a multi-stage production build. The new file is `Dockerfile` at repo root. Old behavior (single-stage `pip install -e .`) is acceptable for local dev only.

```dockerfile
# Stage 1: build wheels
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY contexta ./contexta
COPY alembic.ini ./

RUN pip install --upgrade pip wheel && \
    pip wheel --wheel-dir /wheels '.[prod]'

# Stage 2: runtime
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PORT=8000 LOG_LEVEL=info

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r contexta && useradd -r -g contexta -d /app contexta

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY --from=builder /build/contexta ./contexta
COPY --from=builder /build/alembic.ini ./
COPY scripts/entrypoint.sh /usr/local/bin/contexta-entrypoint
RUN chmod +x /usr/local/bin/contexta-entrypoint && \
    pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

USER contexta

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:${PORT}/healthz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "contexta-entrypoint"]
CMD ["api"]
```

The entrypoint dispatches modes:

```bash
#!/usr/bin/env sh
# scripts/entrypoint.sh
set -e

MODE="${1:-api}"
shift || true

case "$MODE" in
  api)
    exec uvicorn contexta.api.app:app \
      --host 0.0.0.0 --port "${PORT:-8000}" \
      --workers "${UVICORN_WORKERS:-2}" \
      --proxy-headers --forwarded-allow-ips='*'
    ;;
  worker)
    QUEUES="${CONTEXTA_WORKER_QUEUES:-extraction,embedding,maintenance}"
    exec celery -A contexta.workers.celery_app.celery_app worker \
      --loglevel="${LOG_LEVEL:-info}" \
      --queues="$QUEUES" \
      --concurrency="${CONTEXTA_WORKER_CONCURRENCY:-4}"
    ;;
  beat)
    exec celery -A contexta.workers.celery_app.celery_app beat \
      --loglevel="${LOG_LEVEL:-info}"
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  shell)
    exec python -i -c "from contexta.config.settings import get_settings; print(get_settings())"
    ;;
  *)
    echo "Unknown mode: $MODE" >&2
    echo "Usage: api | worker | beat | migrate | shell" >&2
    exit 64
    ;;
esac
```

## How a request flows on the API tier (production)

Order matters. This is what every incoming request sees:

1. **Edge gateway (Go, separate doc 06)** terminates TLS, looks up the API key in Redis (cached), enforces per-key rate limit, checks quota, decorates the request with internal headers (`x-mem-tenant-id`, `x-mem-actor-id`, `x-mem-key-id`, `x-mem-trace-id`), then proxies to API tier or data plane.
2. **uvicorn** accepts the connection, parses HTTP, hands off to FastAPI.
3. **CORSMiddleware** (NEW: not in repo today) checks the `Origin` header against allowed origins from settings.
4. **GZipMiddleware** (NEW: not in repo today) compresses responses larger than 1 KB.
5. **RequestIdMiddleware** (NEW) extracts or generates `traceparent`, sets `request.state.request_id`, attaches to logger context.
6. **AuthenticationMiddleware** (rewrite of existing): trusts internal headers `x-mem-*` from the gateway. If headers are missing (direct hit, never happens in prod) returns 401.
7. **TenantMiddleware** (existing, mostly OK): no-op when gateway is upstream.
8. **AuditMiddleware** (NEW): wraps the response to emit one audit event per state-changing endpoint.
9. **MeterMiddleware** (NEW): emits one usage event per request to Redis Streams.
10. **Route handler** runs. Dependencies (DB session, repos) injected via `contexta.api.deps` (currently empty stub — must be implemented).
11. Response goes back through GZip/CORS, out the door.

For control-plane endpoints (api-keys, sessions, policies, schemas, audit views, explain, timeline) this Python path is fine — these are low-RPS endpoints.

For high-RPS endpoints (`/observations`, `/retrieve`, `/context`, `/memories/{id}/...`) the gateway routes to the **Go data plane** instead. The Python tier is the fallback when Go is down.

## Boot sequence

When a fresh API container starts, in order:

1. `tini` reaps zombies, forwards signals.
2. `entrypoint.sh api` is invoked.
3. Uvicorn imports `contexta.api.app`, which imports `contexta.config.settings.get_settings()`.
4. `Settings()` reads from env vars (and `.env` for local). Missing required values fail fast with a Pydantic validation error (this is correct).
5. FastAPI's `app = create_app()` runs at module import. Middleware chain is registered. Routes are mounted.
6. `app.on_event("startup")` (NEW) executes:
   - `await db.engine.connect()` — verify DB reachable. If not, exit 1 (let orchestrator restart).
   - `await redis.ping()` — verify Redis reachable.
   - `await api_key_cache.warm()` — load active API keys into LRU memory (we still hit DB on miss).
7. Uvicorn binds to port and starts accepting.
8. Healthcheck `/healthz` returns 200 once startup is complete. Until then it returns 503 — Kubernetes/Fly waits for ready before routing traffic.

Workers boot similarly but call `celery_app.control.inspect()` to verify broker connectivity.

`contexta migrate` is a one-shot job. It runs `alembic upgrade head` inside an advisory lock so multiple replicas can boot simultaneously without collision:

```python
# scripts/run_migrations.py
async def main():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT pg_advisory_lock(2305843)"))
        try:
            command.upgrade(alembic_cfg, "head")
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(2305843)"))
```

The advisory lock number `2305843` is arbitrary but reserved for contexta migrations; never reuse it for another lock.

## Routes that need to be added before launch

Currently missing from `contexta/api/`:

| Route | Method | Purpose | Owner |
|---|---|---|---|
| `/healthz` | GET | Liveness — returns 200 if process alive | API |
| `/readyz` | GET | Readiness — checks DB + Redis | API |
| `/metrics` | GET | Prometheus metrics | API |
| `/v1/projects` | GET/POST | Project CRUD | API |
| `/v1/projects/{id}` | GET/PATCH/DELETE | Project detail | API |
| `/v1/keys` | GET/POST | API key CRUD (replaces /api-keys, persisted) | API |
| `/v1/keys/{id}` | DELETE | Revoke key | API |
| `/v1/keys/{id}/rotate` | POST | Rotate key | API |
| `/v1/usage` | GET | Usage rollup for current period | API |
| `/v1/usage/events` | GET | Raw events (last 24h, paginated) | API |
| `/v1/audit` | GET | Audit log query | API |
| `/v1/billing/portal` | POST | Stripe Customer Portal URL | API |
| `/v1/billing/checkout` | POST | Stripe Checkout URL | API |
| `/v1/policies` | GET/POST | Policy CRUD | API |
| `/v1/schemas` | GET/POST | Custom schema CRUD | API |

All existing routes (currently at root: `/api-keys`, `/observations`, `/sessions`, `/memories`, `/retrieve`) get moved under `/v1/` for versioning. The old paths return `301 Moved Permanently` for 90 days.

## What's currently broken or stubbed

These need to ship before the backend is "production runnable":

| Component | Today | Needs |
|---|---|---|
| `contexta/api/deps.py` | Empty | DB session dep, repo factories, current-actor dep |
| `contexta/api/key_store.py` | In-memory dict | Postgres-backed `ApiKeyRepository` with hash + prefix lookup |
| `contexta/api/middleware/auth.py` | Header passthrough | Trust gateway headers in prod, fall back to API key DB lookup in dev |
| `contexta/api/routes/retrieval.py` | Stub returns `{"status": "accepted", "results": []}` | Wire `RetrievalEngine` with real repos |
| `contexta/api/routes/memories.py` | All stubs | Wire `MemoryLifecycleEngine`, `MemoryRepository`, `ContextBuilder` |
| `contexta/api/routes/sessions.py` | All stubs | Wire `SessionRepository`, trigger Epilogue worker |
| `contexta/workers/embedding_tasks.py` | No-op | Implement chained task: dedup → entity-resolve → truth → score → store → embed |
| `contexta/workers/decay_tasks.py` | No-op | Iterate active tenants, run `DecayEngine.run_decay_cycle` per tenant |
| `contexta/workers/reflection_tasks.py` | No-op | Iterate active tenants, run `ReflectionEngine.run_cycle` per tenant |
| `contexta/workers/dream_tasks.py` | No-op | Iterate active tenants, run `DreamCycleEngine.run_cycle` per tenant |
| Logging | `logging.getLogger` only | structlog with JSON formatter, request ID context, tenant context |
| Tracing | None | OpenTelemetry SDK, OTLP exporter to Tempo/Honeycomb |
| Metrics | None | prometheus-client with route latency, queue depth, LLM call counts |
| `app.on_event("startup")` | Not present | Boot checks for DB + Redis + key cache warmup |
| `/healthz`, `/readyz`, `/metrics` | Not present | Add new router |
| CORS, GZip | Not present | Add middleware |

## Production environment variables

Required (process exits 1 if missing):

```env
CONTEXTA_DATABASE_URL=postgresql+asyncpg://contexta:STRONGPASSWORD@db.fsn1.contexta.internal:5432/CONTEXTA_prod
CONTEXTA_REDIS_URL=rediss://:STRONGPASSWORD@redis.fsn1.contexta.internal:6380/0
CONTEXTA_CELERY_BROKER_URL=rediss://:STRONGPASSWORD@redis.fsn1.contexta.internal:6380/1
CONTEXTA_CELERY_RESULT_BACKEND=rediss://:STRONGPASSWORD@redis.fsn1.contexta.internal:6380/2
CONTEXTA_AUTH_SIGNING_KEY=<32-byte base64> # for internal JWTs from gateway
CONTEXTA_GATEWAY_TRUST_PROXY=true
CONTEXTA_LLM_PROVIDER=openai           # default for managed-LLM bundle, BYOK overrides
CONTEXTA_OBSERVABILITY_OTLP_ENDPOINT=https://api.honeycomb.io
CONTEXTA_OBSERVABILITY_OTLP_API_KEY=<honeycomb key>
CONTEXTA_STRIPE_SECRET_KEY=sk_live_...   # API tier only, not workers
CONTEXTA_STRIPE_WEBHOOK_SECRET=whsec_...
```

Optional with safe defaults:

```env
CONTEXTA_FEATURE_DREAM_CYCLE=true       # enable for paid tiers only
CONTEXTA_RETRIEVAL_MAX_LIMIT=100
CONTEXTA_DECAY_ACTIVE_TO_WARM_DAYS=30
CONTEXTA_UVICORN_WORKERS=2              # tune per CPU
CONTEXTA_WORKER_CONCURRENCY=4
CONTEXTA_WORKER_QUEUES=extraction,embedding,maintenance
```

## Memory and CPU tuning

| Process | RAM | CPU | Notes |
|---|---|---|---|
| API container | 2 GB | 2 cores | uvicorn 2 workers |
| Worker (extraction) | 4 GB | 2 cores | LLM payloads can be 1 MB each, holds connection pool |
| Worker (maintenance) | 8 GB | 4 cores | Reflection holds reflection-cycle-sized memory cache |
| Beat | 256 MB | 1 core | Schedule only, no work |
| Postgres | 64 GB | 16 cores | See [05-database-strategy.md](./05-database-strategy.md) |
| Redis | 4 GB | 2 cores | maxmemory-policy=allkeys-lru |

## Graceful shutdown

When orchestrator sends SIGTERM:

1. tini forwards SIGTERM to uvicorn (or celery).
2. uvicorn stops accepting new connections, waits up to `CONTEXTA_GRACEFUL_TIMEOUT_S=30s` for in-flight requests, then exits.
3. Celery worker stops dequeueing, finishes current tasks, exits.
4. Health probe transitions to 503 immediately so the load balancer drains.

## Logging

All logs go to stdout, JSON one line per record. structlog config:

```python
# contexta/observability/logging.py
import structlog, logging, sys

def configure_logging(level: str = "info") -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
```

Every log line carries `request_id`, `tenant_id`, `actor_id`, `endpoint` (set via `contextvars` in middleware).

## Why we still need Python here when Go does the hot path

Three reasons:

1. **LLM calls are Python's home turf.** OpenAI's official Python SDK ships features (Assistants API, structured outputs, batch API) months before Go. Same for Anthropic and LlamaIndex. Worker tier's job is mostly LLM orchestration; reimplementing that in Go would be hostile.
2. **Reflection / dream / clustering are batch.** Latency doesn't matter. CPU is dwarfed by LLM cost.
3. **The control plane (api-keys, sessions, projects, billing) is low-RPS, business-logic-heavy.** Python's velocity wins. Go's perf wouldn't pay off.

Go gets the data plane (next doc 06) precisely because that's where Python costs us money.

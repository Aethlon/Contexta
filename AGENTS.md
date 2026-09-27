# AGENTS.md — Agent & Contributor Playbook for Contexta

Welcome to the Contexta monorepo. This guide defines the system architecture, development conventions, critical invariants, and testing standards for autonomous AI coding agents and human engineers.

> **Start here if you are new:** [`docs/AGENT-1-STATUS.md`](docs/AGENT-1-STATUS.md) is a
> current-state handoff — what is verified working, what was fixed and why, decisions that
> must not be undone, known limitations, and the prioritised next steps. It also records
> three failure modes that caused most of the serious bugs here, so you can avoid repeating
> them. Check it before changing anything, and update it when you finish a workstream.

---

## 1. Monorepo Map & Component Boundaries

| Directory | Stack / Framework | Responsibility |
| :--- | :--- | :--- |
| `contexta/` | Python 3.11+, FastAPI, SQLAlchemy, Celery | **The Brain**: Orchestrates extraction, scoring, truth maintenance, entity resolution, and hybrid retrieval. Sole owner of persistence. Celery workers (`contexta/workers/`) run the extraction, embedding, maintenance, and outbox queues; `contexta/workers/model_server.py` is the local Qwen3 model server on `:8001` and `contexta/workers/inference_server.py` is the fine-tuned extractor on `:8002`. |
| `services/gateway/` | Go 1.22+ | **The Optional Edge**: TLS termination (:8443), Redis-backed API-key verification and rate limiting, and reverse proxy to the Python API. Holds no storage and no staging tables. **Retired as a second entry point** — it is profile-gated behind `edge` in `docker-compose.yml`; the edge capabilities it provided (response cache, single-flight, per-key rate limiting) now live in the Python API as `contexta/api/middleware/{response_cache,ratelimit}.py`. |
| `dashboard/` | Next.js 15, React 19, TailwindCSS 4, NextAuth v5 | **The Operator Console**: Memory inspector, entity graph viewer, API key manager, and live observation ingest. |
| `landingpage/` | Next.js App Router (16.x), React 19, TailwindCSS 4 | **The Public Showcase**: product landing page, benchmark pages, and the marketing changelog. **A separate git repository** (`https://github.com/Jenithpaul/contexta-landing.git`) with its own `node_modules`; it is *not* built by the monorepo compose stack and must not be edited from a Contexta release pass. |
| `docs/` | Nextra 2, Next.js 14, React 18, MDX | **Developer Documentation**: the published guide/reference site plus the long-form Markdown in `docs/Featuers/`. |
| `clients/` | Python (`clients/python`) & TypeScript (`clients/typescript`) | **Agent SDKs**: client libraries exposing `Contexta.observe()`, `Contexta.context()`, `Contexta.retrieve()` and framework adapters. Parity is asserted against `clients/public-api.manifest.json`. |
| `benchmarks/` | Python | LoCoMo and LongMemEval harnesses plus the recorded result artifacts. |
| `tests/` | pytest | The backend suite. `pyproject.toml` holds the only ruff config. |

---

## 2. Core Architectural Invariants

### A. Sovereign, Offline-First Default
* The system must boot and run completely offline without external cloud API keys using local Qwen3 models:
  * Embedding: `Qwen/Qwen3-Embedding-0.6B` (1024 dimensions)
  * Reranker: `Qwen/Qwen3-Reranker-0.6B`
* The model server runs on port `8001` (`contexta/workers/model_server.py`). Online mode (`BYOK` OpenAI/Anthropic/DeepSeek) is strictly opt-in via compose profiles or environment variables (`CONTEXTA_ENGINE_MODE=online`).

### B. Strict Multi-Tenancy Isolation
* **Zero Missing WHERE Clauses**: Every database interaction involving business entities must inherit from `TenantScopedRepository` (`contexta/repositories/base.py`).
* All queries are automatically scoped by `organization_id`. Never bypass repository tenant filtering in API routes.
* **A direct `select()` on a tenant-owned model outside a repository is a security bug, not a style nit.** v1.5 shipped exactly that defect three times and had to fix all of them:
  1. `GET /v1/graph/traverse` resolved the root entity with an unscoped `Entity.name.ilike(...)`, so one tenant could read another tenant's entity names, entity summaries, memory titles, and memory body text, and a name shared across tenants returned a 500.
  2. The MCP `get_metrics` tool used an unscoped `COUNT(*)`, leaking every tenant's row counts to every tenant.
  3. `scripts/enrich_graph.py` performed a cross-tenant `DELETE`.
* If you cannot express the query through a repository, the answer is a new repository method — not an inline `select()`. Regression coverage lives in `tests/test_graph_traverse_is_tenant_scoped.py` and `tests/test_mcp_security.py`.

### C. Ingestion Redaction & Truth Maintenance
* **Secrets Never Enter Memory**: Ingestion runs regex sanitization in `contexta/core/extraction/sensitive_filter.py` before extraction, to redact API keys, JWTs, bearer tokens, passwords, OTPs, session cookies, and card numbers. The gate is **fail-closed**: if it errors, the observation is rejected rather than forwarded unredacted (`FastMemoryOrchestrator._redact_payload`).
* **One current fact per slot**: a `subject`/`predicate`/`object` triple from the extractor yields a structural slot key `sfx1:<sha256>`, so a corrected value *supersedes* the row it replaces instead of accumulating a second vector. Legacy bare-64-hex text-hash keys are still produced for any extraction with no usable triple and are still supported.
* **No Vector Accumulation Contradictions**: When a new observation updates or contradicts an existing memory, the truth engine (`contexta/core/truth/maintenance.py` and `contexta/core/truth/service.py`) must invalidate the old record (`valid_to = now()`) and link the lineage via `MemoryVersion.superseded_by_id`. Stale facts are excluded from active retrieval. The database enforces this with `uq_memory_record_current_fact_slot`, a partial unique index over `(organization_id, user_id, fact_key)` restricted to `valid_to IS NULL` — so a correction *must* supersede; it cannot coexist.

### D. Hybrid 3-Layer Retrieval
* High-salience recall fuses:
  1. Dense vector cosine similarity via pgvector HNSW.
  2. Lexical keyword matching via PostgreSQL TSVECTOR GIN index (BM25).
  3. Multi-hop knowledge graph traversal via entity relationship edges.
* Channel weights default to `dense 0.5 / lexical 0.3 / graph 0.2` (`RetrievalEngine.DEFAULT_CHANNEL_WEIGHTS`), fused by weighted Reciprocal Rank Fusion with `k = 60` (`contexta/core/retrieval/fusion.py`).
* **Cascade mode is opt-in and off by default.** `RetrievalEngine(enable_dense_escalation=True)` inverts the order: lexical and graph gather evidence first, and `assess_primary_sufficiency()` decides whether the dense channel is needed at all. There is no environment variable and no request field for it — the only switch is the constructor argument. Do not add one without a measured escalation rate.
* Every retrieved memory hit must trigger read-age decay updates via `touch_accessed()`.

### E. No Billing or Metering Code
* Billing and usage metering have been permanently excised from Contexta Core. Do not re-introduce Stripe/Dodo checkout, billing webhooks, or credit deduction middleware.
* This is now backed by the schema, not just by convention: Alembic revision `020` drops 18 billing tables and 6 dead domain schemas, taking the public table count from 57 to 33.
* The repository is dual-licensed, not Apache 2.0 outright — see the root `LICENSE`. Apache 2.0 covers personal/hobbyist/non-commercial self-hosting and internal development; business environments, production enterprise, and any use where Contexta powers a commercial product or SaaS need a paid commercial licence. Do not document the project as flat "Apache 2.0".

---

## 2b. v1.5 Current State

Read this before planning work. These are measured facts, not intentions.

| Fact | Value | Where it comes from |
| :--- | :--- | :--- |
| Alembic head | `020` (`contexta/migrations/versions/20260926_0020_drop_dead_schemas.py`) | `revision = "020"` |
| Public tables | 33, down from 57 | 18 billing tables + 6 dead schemas dropped by `020` |
| Backend test suite | **392 passed, 0 failed, 0 skipped** | `.venv\Scripts\python.exe -m pytest tests/ -q` |
| Focused quality gate | 58 tests across temporal, ingestion outbox, fusion, and retrieval | `tests/test_temporal_normalization.py tests/test_ingestion_outbox.py tests/test_retrieval_fusion.py tests/test_retrieval_engine.py` |
| Package version | `pyproject.toml` still declares `version = "0.1.0"` | Unchanged on purpose; do not silently bump it as part of unrelated work. |
| Dashboard auth | **Off by default**, `CONTEXTA_DASHBOARD_AUTH` (`off` \| `on`) | `dashboard/src/lib/dashboard-identity.ts` |
| Auth transport | One API key carries both organization and actor; identity headers are optional cross-checks | `contexta/api/middleware/auth.py` |

### Revisions 015-020

| Revision | What it does |
| :--- | :--- |
| `015` | Storage and graph indexes for the hot paths, including a rebuilt `memory_record` partial index and a leading `entity_id` index on `memory_entity_link` |
| `016` | Composite bitemporal index on `memory_record (organization_id, user_id, valid_from, valid_to)`, making `as_of` an index scan |
| `017` | `api_key.tier` with a CHECK constraint, so rate limiting meters per tier instead of one hard-coded limit |
| `018` | Case-insensitive uniqueness on `(organization_id, user_id, lower(name))` for `entity`, plus a closed relationship-type CHECK and self-loop rejection. Merged 2,670 duplicate entity groups to zero and deduplicated 2,745 colliding edges; 869 relationship types were normalised. |
| `019` | `uq_memory_record_current_fact_slot`, a partial unique index guaranteeing one current row per fact slot |
| `020` | Drops 18 billing tables and 6 dead domain schemas |

### Measured performance

| Path | Before | After |
| :--- | ---: | ---: |
| Lexical GIN search | ~550ms | ~48ms |
| `as_of` bitemporal read | ~46ms | ~0.22ms |
| Recursive-CTE graph traversal | ~38.5ms | ~2.16ms (~16x) |
| Session-level extraction success | ~17% | 87.5% |

Extraction context was raised from 4,096 to 16,384 tokens (real prompts are 8,281). Ollama's OpenAI-compatible `/v1/chat/completions` **silently drops the `format` field**, so structured output was never actually constrained; Contexta now detects an Ollama endpoint and uses the native Ollama route.

### Dashboard auth switch

The operator console runs **without a sign-in by default**, because Contexta is a self-hosted, single-operator tool. Set `CONTEXTA_DASHBOARD_AUTH=on` to restore the NextAuth v5 credentials flow. The tenant resolves in order from the `contexta_tenant` cookie, then `CONTEXTA_DASHBOARD_ORG_ID` / `CONTEXTA_DASHBOARD_USER_ID`, then `CONTEXTA_DASHBOARD_API_KEY` (the console asks the API which organization that key belongs to). The operator can see and change the active tenant in the UI. If nothing resolves, the console reports "unresolved" and its API calls go out unauthenticated rather than silently acting on another organization.

**With auth off, the console must not be exposed to an untrusted network.** `docker compose.yml` now passes `CONTEXTA_DASHBOARD_AUTH` and `CONTEXTA_DASHBOARD_API_KEY` through to the container so the operator does not have to paste a key by hand.


---

## 3. Development Workflow & Commands

### Running Services (Universal Cross-Platform):
```bash
# macOS & Linux:
./entrypoint.sh           # Default offline-first stack in background
./entrypoint.sh dev       # Foreground with live streaming logs
./entrypoint.sh status    # Check container health
./entrypoint.sh stop      # Graceful shutdown

# Windows (PowerShell):
.\start.ps1               # Default offline-first stack
.\start.ps1 dev           # Foreground with live logs
.\start.ps1 stop          # Graceful shutdown

# Or via Docker Compose directly:
docker compose up --build
```

### Local Dashboard (`dashboard/`):
```bash
cd dashboard
bun install
bun run dev      # Runs on http://localhost:3000
bun run build    # Verify production compilation
```

### Python Backend & Tests (`contexta/`):
```bash
# Run test suites from the repository root:
uv run pytest tests/ -q
.venv\Scripts\python.exe -m pytest tests/ -q   # Windows venv

# Run targeted suites:
uv run pytest tests/test_retrieval_engine.py tests/test_api_keys.py -v

# Lint (ruff config lives in pyproject.toml):
uv run ruff check contexta tests
```

### Go Service (`services/gateway/`):
```bash
cd services/gateway && go build ./...
cd services/gateway && go vet ./...
```

---

## 4. Key Directory & Model Conventions

1. **API Routes**:
   * Stored in `contexta/api/routes/`.
   * Mounted in `contexta/api/app.py`.
   * Tenant context comes from the authenticated API key (which supplies both organization and actor). Identity headers are optional cross-checks, not the primary proof — see §2b.

2. **Dashboard Server Actions**:
   * Stored in `dashboard/src/app/actions.ts`.
   * Always use `contextaFetch()` from `@/lib/auth-helpers` to automatically attach the resolved operator identity.

3. **Vector Dimension Rule**:
   * Offline Qwen3 = 1024 dimensions.
   * Online OpenAI = 1536 dimensions.
   * Do not mix dimensions without running a pgvector column migration or re-creating the database volume (`docker compose down -v`).

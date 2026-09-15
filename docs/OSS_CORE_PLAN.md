# Contexta OSS Core Plan — handoff for next session

> Status: OSS v1 in progress. Billing removed. Go = data-plane, Python = brain.
> Run: `docker compose up --build` (personal local, offline-first).
> Profiles planned: `--profile online`, `--profile enterprise`.

## 1. TSVECTOR vs HNSW — why both?

Both live on `memory_record` (`contexta/models/memory.py`):

- **HNSW (`ix_memory_record_embedding_hnsw`, `vector_cosine_ops`, m=16, ef=64)** = semantic / fuzzy search.
  - Q: "user likes boutique hotels" matches "prefers historic inns" even with zero shared words.
  - Cost: approximate, needs embedding on every row + query. NULL embeddings score 0. Falls apart on exact tokens (names, IDs, versions, typos-as-typed).
- **TSVECTOR + GIN (`search_vector`, trigger-maintained `title+content`)** = exact / keyword search.
  - Q: `PostgreSQL`, `project-apollo-42`, error strings. BM25-style lexical rank, stemming, prefix. No embedding needed, cheap, deterministic.
  - Falls apart on paraphrase ("db" vs "database").

God-tier retrieval needs both + graph, fused with RRF. Neither alone is enough.
Rule: HNSW for meaning, TSVECTOR for precision, graph for relations, reranker for truth.

## 2. Dynamic DB — fast memory + deep data, retrieval must not block

Latency budget for `retrieve`: p50 < 80ms local, p95 < 250ms (excluding LLM call).

```
L1 HOT (Redis, ms)               L2 WARM (Postgres, 10s of ms)            L3 DEEP (Postgres, background)
- apikey:<sha256>                - memory_record + Vector(1024/1536)      - memory_version (superseded chain)
- graph:{user}:adj:{entity}      HNSW + TSVECTOR GIN + (org,user,state)   - compressed_summary / semantic_cluster
- ctx:{query_hash}:{budget} 300s - entity / entity_edge(typed+weight)     - dream_record / gaps
- embed job queue (Stream)       - memory_entity_link                    - audit / feedback aggregates
```

Write path (async, never block SDK):
`SDK -> Go receiver :8443 (validate <10ms, 202 job_id) -> Postgres staging + Redis stream -> Celery worker (classifier JSON -> dedup -> score -> graph -> embed Qwen3/openai -> truth) -> L2/L3 + invalidate L1`.

Read path (sync, hot only):
`query -> Go data-plane :8080 -> L1 check -> L2 parallel (HNSW filtered valid_to IS NULL + FTS + 2-hop graph from L1 adjacency) -> RRF fuse top 45 -> Qwen3-Reranker-0.6B top 15 -> rescore (sem/rerank/graph/keyword/recency/importance/utility) -> MMR diversity -> token-budget planner -> L1 cache + touch_accessed (async fire-and-forget)`.

Key fixes queued:
- `retrieval/engine.py:385` recency computed but unused — wire into score.
- `memory_repo.py vector query` unfiltered — add `valid_to IS NULL, is_archived=False`.
- `feedback.py` in-memory only — persist to `utility_score`, feed back to rank.
- `touch_accessed()` never called — decay currently uses write-age, must use read-age.
- `NULL` embeddings between insert and backfill — backfill worker 1m beat + sync embed on `remember` fast path for OSS single-node.
- Dual dims: offline 1024 (Qwen3-Embedding-0.6B), online 1536 (openai text-embedding-3-small). Schema currently `Vector(1536)` hardcoded — needs per-mode migration.

## 3. Core logic (agreed)

- Auth: API-key-only (`/v1/keys` GET/POST). No signup/signin in OSS. Python must publish `apikey:<sha256>` to Redis on create; scopes `read/write`; Go forwards `Authorization: Bearer + x-organization-id`.
- Modes: `offline` = Qwen3-Embedding-0.6B + Qwen3-Reranker-0.6B auto-downloaded to `./models` via `scripts/download_offline_models.py`, served by `model-server:8001` (load-once, micro-batch 5ms/32). `online` = BYOK classifier LLM (any OpenAI-compatible) + OpenAI embedder (cheapest). `auto` = cloud first, circuit-breaker fallback to local.
- Default = personal local memory layer, MCP-compatible (`contexta/mcp/service.py`: remember/recall/get_context/explore_graph) for Claude/OpenAI/any MCP client.
- Enterprise profile (later): strict org isolation, per-org pools, audit, gateway enforcement. Not default.
- Ingest contract: `observe(user_id, messages[]) -> classifier strict JSON {memories[{type,title,content,entities[],relations[],importance_hint}]} -> embed(title+\n+content)`.
- Web (`web/`) + Python core (`contexta/`) + Docker are the OSS surface. One command boots postgres+pgvector, redis, api, worker, beat, model-server, web.

## 4. OSS cut done (this session)

Deleted:
- `contexta/api/routes/billing.py` (Dodo checkout/portal/usage/webhooks)
- `contexta/services/dodo_billing.py`
- `contexta/models/usage.py` (`UsageEvent/UsageDaily/UsagePeriod`)
- `services/aggregator/` (usage rollup consumer, schema-mismatched)
- `aggregator` service in `docker-compose.yml`, `billing_router` in `contexta/api/app.py`, usage exports in `contexta/models/__init__.py`

Kept intentionally (billing tables in migration `003` still create unused tables — squash later; `auth.py` kept until API-key-only middleware lands; `settings.dodo_*` harmless).

## 5b. Phase-1 progress (2026-09-10, done)

- API keys publish `apikey:<sha256>` to Redis on create + delete on revoke (`repositories/api_key_repo.py`). Best-effort, Postgres stays source of truth.
- Default scopes now `["read","write"]`; Gateway accepts `read/write/admin/observe/retrieve` (`services/gateway/internal/server/server.go:scopeMiddleware`).
- Gateway forwards `x-organization-id/x-user-id` plus `X-Mem-*` (`internalHeadersMiddleware`); Python `auth.py` + `tenant.py` accept both.
- Added `DELETE /v1/keys/{key_id}` (web key manager was 405).
- Removed `/v1/webhooks/dodo` from public paths.
- Gateway `/api/v1/*` now strips `/api` prefix (`proxy.go:StripPrefixReverseProxy`) so it hits real Python `/v1/*`.
- New migration `005` creates Go `observations`/`sessions` compat tables (unblocks data-plane `UndefinedTable`).
- Retrieval scoring now uses `recency + utility + confidence` (`core/retrieval/engine.py:_score_memory`), cold penalty is smooth `*0.7`, vector query filters `valid_to/archived/NULL embedding` (`repositories/memory_repo.py`).
- Verified: `test_api_keys + test_retrieval_engine` 6 passed, endpoint suites 39 passed, `go build` gateway + data-plane clean.

## 5c. Phase-2 progress (2026-09-10, done)

- Model-server is Qwen3-first: `DynamicMicroBatcher` tries local
  `models/qwen3-embedding-0.6b` via sentence-transformers, falls back to
  FastEmbed bge-small, then hash (`workers/model_server.py`). Reranker tries
  local Qwen3-Reranker CrossEncoder (`predict` API), then bge-reranker, then
  heuristic. `/v1/classify` is neural-first (embedding cosine to label
  prototypes blended with keyword prior) with keyword fallback only when no
  neural backend exists. `/models/status` reports actual backends.
- Retrieval calls `touch_accessed()` on final hits, so decay uses read-age
  (`core/retrieval/engine.py:_touch_accessed`, best-effort).
- Bulk resolver emits typed relations via `extract_semantic_relations()`
  (uses/depends_on/prefers/...) with RELATED_TO fallback, not a
  RELATED_TO-only clique.
- Truth maintenance no longer writes entity->self SUPERSEDED_BY self-loops;
  lineage lives in `MemoryVersion.superseded_by_id` + audit
  (`core/truth/maintenance.py`). Test updated accordingly.
- Compose is offline-first: api/worker default to local Qwen3/1024-dim via
  env (`${CONTEXTA_*:-}`), beat got `DATABASE_URL`+`REDIS_URL`,
  `web/next.config.ts` has `output:standalone` (runner CMD was broken).
  `.env.example` documents offline defaults + online (1536-dim) examples.
  Settings defaults flipped to local/Qwen3/1024.
- Fixed pre-existing `BASE_SCORES` gap for `PROCEDURAL`/`RULE` types.
- Verified: full suite 241 passed (1 env-only fail: `test_mcp_server`
  needs live Postgres, same as local PG password issue), `go build` clean.

## 5d. Phase-3 progress (2026-09-10, done)

- Decision: password auth (`auth.py` signup/signin) stays — web dashboard
  login (NextAuth) depends on it. API-key-only is the agent/SDK path.
  Full web rewrite to key-only login is deferred, not deleted blindly.
- Web scope canonicalization: new keys default to `read,write`
  (`actions.ts`, `api/keys/route.ts`, `api-key-manager.tsx` options).
  Gateway accepts old `observe/retrieve` too, so existing keys keep working.
- New `docker-compose.online.yml` (BYOK LLM + OpenAI 1536-dim) and
  `docker-compose.enterprise.yml` (gateway enforcement, eager off,
  secret required, worker limits). Both validate with `docker compose config`.
- README: offline-first quickstart (`cp .env.example .env && up`, no keys),
  profiles, dimension-switch warning, corrected MCP section (stdio default,
  SSE on :8765 via `python -m contexta.mcp` — NOT :8000/sse, that route
  doesn't exist on the API app).
- Verified: 16 passed (model_server/api_keys/retrieval/truth/endpoints).

## 5e. Phase-4 progress (2026-09-10, done)

- Pipeline scores with real signals: `ImportanceSignals(mention_count=
  len(entities), has_emphasis, impacts_decisions)` in `orchestrate()` and the
  `MemoryPipeline` fallback (`core/pipeline.py`). Mention-count updates for
  matched entities are now flushed via `update_by_id` (were collected then
  dropped).
- Dream task rewritten: was triple-broken (`datetime.now(UTC())` TypeError,
  `sync_session_factory` ImportError, NULL-`last_accessed_at` exclusion).
  Now async impl + sync wrapper like other workers, 24h dormant cutoff,
  NULLs included (`workers/dream_tasks.py`).
- Agentic engine fixed: substring intent matching ("used to"/"blocked by"
  now fire), score-weighted entity pick (not alphabetical), sub-retrievals
  keep `query_embedding`, `supersedes_id` getattr guard (was AttributeError
  crash on MemoryRecord) (`core/retrieval/agentic_engine.py`).
- Go loop closed: new `drain_go_staging` task converts `observations`
  staging rows (status='active') to ObservationPayloads, runs the
  orchestrator, marks rows processed/skipped; beat every 60s
  (`workers/extraction_tasks.py`, `workers/celery_app.py`). Go ingest is no
  longer a black hole.
- Verified: full suite 241 passed (mcp live-DB + speed excluded, same env
  reasons as before).

## 5f. Phase-5 progress (2026-09-10, done) — billing/metering fully removed

Web deleted:
- `dashboard/billing/page.tsx`, `dashboard/usage/{page,usage-chart}.tsx`
  (orphaned: never in sidebar nav; hit deleted `/v1/billing/*`, `/v1/usage`).
- Dead actions in `actions.ts`: `getUsageAction`, `createCheckoutSessionAction`,
  `openCustomerPortalAction`.
- Dashboard overview now shows Stored memories / Active keys / Recent events
  (was billing-period Observations/Retrievals from dead endpoint).
- Settings page: Usage Summary card removed; provider defaults corrected to
  local/Qwen3; env table updated. Docs endpoint table: `/v1/usage` row removed
  (already listed `DELETE /v1/keys/{id}`).

Go deleted:
- Whole `data-plane/internal/metering` package (`meter:events` stream had no
  consumer since aggregator removal — pure per-request Redis overhead).
- `Emitter` field/param/wiring (`server.go`, `main.go`) + all 7 `Emit` calls
  (observations x2, memories x5). Structured `slog` lines kept.

Python deleted:
- `settings.dodo_*` fields, `services/__init__` billing mention,
  `OrganizationRepository.find_by_customer_id` / `update_plan` (only the
  deleted billing route used them).
- Kept: `account.dodo_customer_id/subscription_id` columns (migration 003
  compat, nullable, inert — drop in a future squash).

Verified: `go build` clean (gateway + data-plane), pytest 33 passed
(api_keys/endpoints/observations/repositories), `tsc --noEmit` clean
(only errors were stale `.next` cache refs to deleted pages; cache cleared).

## 5g. Phase-6 progress (2026-09-10, done) — new Vite landing page

New `landing/` app (Vite + React 19 + Tailwind v4 + MDX). `web/` stays
dashboard-only. Verified: `bun install` clean, `tsc --noEmit` clean,
`vite build` → `dist/` in ~2s.

- Theme: black & white + dark ash gray only (`src/theme.css`:
  `--color-ash-950…700`, `--color-ink-*`). No gradients, no borders —
  depth from flat ash elevations + radius.
- Hero (`Hero.tsx` + `IsoFlow.tsx`): centered headline, Console/GitHub
  CTAs, honest chips, then the isometric system diagram — SDK → Gateway
  → Data-Plane (READ lane) / Python Brain (WRITE lane) → Qwen3 embed link
  → L1/L2/L3 plates → inverted Context node. Animated dash connectors
  (reduced-motion respected), dot-grid floor, mono port tags.
- Nav/tabs: Docs, Architecture, Contribute + GitHub link + Console button
  only. All outbound links in `src/site.ts` (GitHub URL is a placeholder).
- Docs: hash-routed MDX viewer (`Docs.tsx`), pages in `src/docs/`
  (quickstart, architecture, contributing). Add a file + one entry to add
  a page. Contribution guide doubles as the OSS invite.
- Vercel: `vercel.json` pins framework=vite, `bun run build` → `dist/`,
  SPA rewrite included. Root directory = `landing`. No env vars needed.
  Deploy notes in `landing/README.md`.
- `web-public/` (old Next.js landing) left untouched but NOT Vercel-ready:
  11 files import `@aethlon/components` (external `file:` dep outside this
  repo → install fails on Vercel). Recommend deleting it once `landing/`
  ships. Decision needed: real GitHub URL + Console URL for hosted dash.

## 5h. Phase-7 progress (2026-09-11, done) — Dashboard Renamed, Wired up & Observation Ingest Added

- **Directory Rename**: `web/` renamed to `dashboard/`. Updated `dashboard/Dockerfile` (`COPY dashboard/...`) and `docker-compose.yml` (`context: .`, `dockerfile: dashboard/Dockerfile`, service `dashboard:`).
- **Audit Logging Connected**:
  - Implemented `GET /v1/audit` in `contexta/api/routes/audit.py` with tenant scoping and `created_at DESC` sorting via `AuditRepository`.
  - Mounted `audit_router` in `contexta/api/app.py`.
  - Dashboard overview page (`dashboard/src/app/(dashboard)/dashboard/page.tsx`) now receives real audit events via `getAuditLogAction()`, unblocking the "Recent events" counter.
- **Memory Inspector Hybrid Search Wired**:
  - `dashboard/src/app/(dashboard)/dashboard/memories/page.tsx` now awaits `searchParams`.
  - Passing `?q=...` executes `getMemoriesAction(q)` against `POST /v1/retrieve`, displaying search results with a clear filter badge.
- **Interactive Observation Submission**:
  - Added `ingestObservationAction()` in `dashboard/src/app/actions.ts` targeting `POST /v1/observations`.
  - Added `IngestObservationModal` in `dashboard/src/components/ingest-observation-modal.tsx` and mounted it into the global dashboard header (`layout.tsx`). Operators can now submit live test conversations directly from the dashboard and immediately view extracted memories.

## 6. Project Vision: What We Want to Achieve

Contexta is the sovereign, open-source memory intelligence layer for autonomous AI agents.

### The Big Idea:
1. **Persistent Memory Between Context Windows**: Stateless agents forget facts across turns or hallucinate when context windows overflow. Shoveling full transcripts into prompts degrades attention ("lost in the middle") and quadruples token costs. Contexta stores structured knowledge outside the prompt and injects only high-utility, truth-maintained facts at inference time.
2. **Temporal Truth Maintenance**: When user states change ("I used MySQL, now I migrated to Postgres"), naive vector stores return both contradictory facts. Contexta versions superseded memories, marks `valid_to = now()`, and eliminates contradictions before retrieval.
3. **Hybrid 3-Layer Recall**: Fusing pgvector HNSW semantic embeddings + PostgreSQL TSVECTOR BM25 lexical keyword matching + multi-hop knowledge graph expansion via Reciprocal Rank Fusion (RRF), capped by Cross-Encoder neural reranking.
4. **Offline-First Sovereignty**: Zero cloud dependencies required. Boots completely self-contained with local Qwen3-0.6B embedding and reranking micro-batchers.

---

## 7. What To Do Next (Prioritized Milestones)

1. **Unblock & Complete 50k Benchmark Run**:
   - `models/benchmark_jobs.json` shows job `bench-b3d02750` interrupted at 35.6% (178/500 queries) due to server restart.
   - Script runner must be resumed and results persisted to generate public accuracy/latency charts.
2. **Model-Server Auto-Download Check**:
   - Verify `scripts/download_offline_models.py` triggers automatically if `./models/qwen3-embedding-0.6b` is missing on first boot.
3. **SDK Packaging & Registry Releases**:
   - Publish `contexta-client` to PyPI and `@contexta/client` to npm.
   - Clean up placeholder install commands across landing pages (`pip install contexta-ai` / `npm i @contexta/sdk` are currently placeholders).
4. **Vector Dimension Migration Utility**:
   - Provide a clean migration command to convert pgvector columns when switching between offline mode (1024 dimensions) and online mode (1536 dimensions).
5. **MCP Server Live Integration**:
   - Run live automated integration tests between `contexta/mcp/service.py` and real Claude Desktop / cursor MCP clients.

---

## 8. Known Bugs, Quirks & Gotchas Registry

| Item | Issue | Status / Workaround |
| :--- | :--- | :--- |
| **Audit Route 404** | Dashboard requested `/v1/audit` which did not exist on Python backend. | **FIXED in Phase 7**: Added `contexta/api/routes/audit.py`. |
| **Memory Search Ignored** | Memory Inspector typed query was ignored by `page.tsx` searchParams. | **FIXED in Phase 7**: Wired `searchParams.q` to `getMemoriesAction`. |
| **Interrupted Benchmark Job** | `bench-b3d02750` interrupted at 35.6% in `models/benchmark_jobs.json`. | **OPEN**: Re-run benchmark script using `scripts/run_benchmarks.py`. |
| **Vector Dimension Lock** | Schema `Vector(1536)` vs `1024` offline Qwen default causes pgvector dimension errors if switched without recreation. | **WORKAROUND**: Use fresh volume (`docker compose down -v`) when flipping offline ↔ online modes until dynamic column migration lands. |
| **Web-Public External Dep** | `web-public` imports `@aethlon/components` via `file:../../Aethlon_polyrepo/components`. | **WORKAROUND**: Use `landing/` for standalone/Vercel deployments. |
| **MCP Server Test Requirement** | `test_mcp_server` requires live running Postgres service. | **EXPECTED**: Requires live DB container running. |


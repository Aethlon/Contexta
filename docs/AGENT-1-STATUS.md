# Agent 1 — Status Handoff

**Owner:** Agent 1 (this workstream)
**Last updated:** 2026-09-26
**Branch/worktree:** dirty by design — 244 changed paths, **nothing committed**
**Purpose of this file:** let the next agent (human or otherwise) understand what is
actually true right now, what was verified, and what to do next — without re-deriving
it from scratch.

---

## 1. Read this first: the three rules that were violated

Nearly every serious bug found in this workstream came from the same three places.
Do not repeat them.

| Rule | Why |
| --- | --- |
| **Deployed code must match source.** | The model-server container was running the *old* image for the whole session (`backend: fastembed`) while the source said Qwen3-only. Every test passed against code nobody was shipping. Always `docker compose up -d --build <svc>` after changing a service, and check `/health` for the expected backend string. |
| **Never let a failure path be silent.** | `error=recall_failed` with no message, a bare `suppress(Exception)` around a Celery publish, and `raise` inside a `finally` (which swallows the traceback) together hid a dead endpoint, a dead queue, and a `TypeError` for an entire session. Log the exception *type and message* at minimum. |
| **Verify at the boundary the user touches.** | `/v1/kernel/recall` returned 500 and `/v1/graph/traverse` raised `NameError`, and neither was caught until a test supplied real parameters. A 422 from a smoke test is not evidence a route works. |

---

## 2. What this system is

Contexta is a persistent memory engine for AI agents. The flow:

```
client / agent  ──▶  Python API (:8000)  ──▶  Postgres  +  Redis outbox
                                                   │
                                                   ▼
                                          Celery worker ──▶ fine-tuned LFM2.5-1.2B
                                          (fine-tune :8002)     extraction
                                                   │
                                                   ▼
                                    memories → Qwen3 embed (:8001) → HNSW
```

Non-obvious architecture decisions currently in force:

- **Python is the only data path.** The Go data-plane was deleted; Go survives only as a
  stateless edge and is gated behind the `edge` compose profile.
- **The only public entry point is the Python API on `:8000`.** Response caching,
  single-flight coalescing and rate limiting live *inside* Python as middleware.
- **The extractor is a fine-tuned local model**, reached through the inference server's
  contract-native `/v1/extract`. It is not a prompt-engineered cloud call.
- **Redaction happens before extraction**, in-process, in pure code. No model is in the
  redaction path.

---

## 3. Running the stack

```powershell
docker compose up -d --build          # full stack
docker compose up -d --build api worker beat   # after editing those three
docker compose ps                     # api/worker/beat MUST be "running"
```

Services: `postgres` `redis` `model-server` `inference-server` `api` `worker` `beat`
`dashboard` `mcp` `aggregator` (+ `gateway` only under `--profile edge`).

> **`mcp` requires an API key.** It fails closed: without `CONTEXTA_MCP_API_KEY` it
> refuses to start and compose will restart-loop it. A local dev key is already
> written to the gitignored `.env`; regenerate with
> `uv run --no-sync python benchmarks/mint_mcp_key.py`. Set
> `CONTEXTA_MCP_ALLOW_ANONYMOUS=true` only for a single-tenant experiment.

> **Known trap:** `api`, `worker` and `beat` have silently sat in `created` state
> (never started) while everything *looked* healthy. A stopped Docker Desktop will
> leave them there. Always confirm with `docker compose ps`.

Migrations: DB is at **`020`**. After adding one, run
`docker compose build migration && docker compose run --rm migration` — a bare
`run` reuses the stale image and silently does nothing.

---

## 4. Verified working

Every item below was executed and observed. The scripts are the evidence; re-run them
rather than trusting this table.

| Check | Command | Result |
| --- | --- | --- |
| API surface, 25 endpoints | `uv run --no-sync python benchmarks/api_smoke_test.py` | **25/25 pass** |
| Ingest → real memory | `uv run --no-sync python benchmarks/extract_e2e_test.py` | **PASS**, 4 memories with S-P-O |
| Redaction | `uv run --no-sync python benchmarks/redaction/run_redaction_test.py` | **0 leaks, 0 over-redactions, 59/59 idempotent** |
| Cache / rate-limit middleware | `uv run --no-sync python -m pytest tests/test_api_middleware.py` | **11/11 pass** |
| MCP security (unit) | `uv run --no-sync python -m pytest tests/test_mcp_security.py` | **22 pass, 2 skip** (the 2 need a live DB) |
| MCP security (live, in-container) | `docker cp benchmarks/mcp_security_check.py memento-worker-1:/app/ && docker exec memento-worker-1 python /app/mcp_check.py` | **4/4 pass** |
| Graph traversal | `uv run --no-sync python benchmarks/graph_endpoint_test.py` | **all endpoints 200** |
| Go edge | `cd services/gateway; go build ./... && go test ./...` | **build ok, tests ok** |
| Compose | `docker compose config --quiet` | **valid** |

> **Run the two MCP checks inside a container.** `localhost:5432` on this host is a
> *different* Postgres (`mel-postgres`), so DB-backed tests fail on the host with
> `InvalidPasswordError` even though the credentials look right. Use the worker
> container, which resolves `postgres:5432` correctly.

Healthy runtime state: model server reports
`{"embedding": "qwen3", "reranker": "qwen3"}`; inference server serves
`contexta-lfm-extract`; all 22 observations `completed` (none stuck); DB at migration
`020`.

### Fine-tuned model

- `LiquidAI/LFM2.5-1.2B-Instruct`, LoRA r=16 → merged → **Q4_K_M GGUF**, registered in
  Ollama as **`contexta-lfm-extract`**.
- Held-out (105 rows): 100% valid JSON, 100% exact claim set, 100% category/status/
  object/predicate match, ~2.3 s latency. Base model: 47.5% valid JSON, 0% exact.
- Q4_K_M was lossless for this task.
- The contract lives in **`contexta/contracts/extraction.py`** and is imported by the
  benchmark harness, the inference server and the model-server prompt. It exists
  because those three had drifted into three incompatible shapes and the model scored
  0% on the one it was *not* trained on. **Do not fork the schema.**

---

## 5. What Agent 1 fixed, and why it mattered

Grouped because the causes are more useful than the symptoms.

**5.1 The ingestion pipeline was dead — three separate causes**
- Outbox events were *claimed* by a Celery `task_success` signal that never fired, so
  they were leased and never extracted. Replaced with an inline publish in
  `outbox_tasks._publish_claimed_events`.
- `_pending_organization_ids_async` filtered `status IN ('pending','failed')` while the
  claim query also accepts expired `'claimed'` rows — any orphaned claim became
  permanently invisible.
- `fail_attempt`/`complete_attempt` live on `IngestionObservationRepository` but query
  `IngestionAttempt`, so `_scope_select()` injected `ingestion_observation.organization_id`
  into a `FROM ingestion_attempt` query. A cross join with no `ON`, which multiplied
  rows and raised `MultipleResultsFound`. **This was a tenant filter applied to the
  wrong table** — a correctness bug, not just an availability one.

**5.2 Observations wedged in `processing` forever**
A failure *before* an attempt row existed never released the lease, so every retry was
skipped as "already claimed", and after `max_attempts` the row was stranded with no
terminal transition. Added `_release_claim_after_failure`, which releases the lease or
dead-letters. Also fixed `attempt_number`, which was derived from a denormalized
counter while uniqueness is on `(observation_id, attempt_number)` — now read from
`MAX(attempt_number)` with an `IntegrityError` stand-down.

**5.3 The fine-tuned model was dead code**
`LLMService._call_local_model_server` never called a language model. It hit
`/v1/classify` for a coarse label and hand-built memories from a capitalised-word
regex, while `CONTEXTA_LLM_MODEL` was set to a *reranker* and the base URL was empty.
Rewired to the inference server, with the regex assembler kept only as a loudly-logged
last resort.

**5.4 Endpoints that had never worked**
- `/v1/kernel/recall`: `_optional_uuid()` declared with 1 parameter, called with 2 at
  12 sites → `TypeError` → 500 on every call.
- `/v1/graph/traverse`, `/v1/entities/traverse`: `MemoryEntityLinkRepository` used but
  never imported → `NameError` on every call.
- `/v1/observations` accepted `{"messages": []}` with a 202, creating rows that can
  never produce a memory.
- `primary_scan` never covered personal data: names, emails, phones, addresses, SSNs,
  health facts all leaked (41 of 59 cases). Now **0**.

**5.5 A model-level bug that broke every import path**
`models/entity.py` declared its unique identity index as
`Index(..., func.lower(column("name")))`. `column("name")` builds an *anonymous Column*,
so SQLAlchemy raised `Can't add unnamed column to column collection` when the class was
declared — killing the whole MCP container, and any import that reached
`contexta.models` via `core.dream.engine`. Correct expression form is
`func.lower(text("name"))`.

**5.6 Consolidation**
Go data-plane deleted (14 files, 0 tests, unwired, no indexes on its tables). Its
capabilities were ported into Python first so nothing was lost. The Go gateway is
`profiles: ["edge"]` and out of the default stack.

---

## 6. Deliberate decisions — do not undo these without new evidence

| Decision | Rationale |
| --- | --- |
| **Do not backfill the 71k legacy vectors.** | Verified: all 26 memories written in the last hour have `embedding_profile=offline-qwen3-1024`, 1024 dims, correct column, zero legacy vectors. The new-data path is correct. The 71k rows are *benchmark fixtures* (one user alone has 40,013), not product data. Re-embedding them is a benchmarking concern; re-importing through the working pipeline is cheaper and exercises the real path. |
| **No automatic re-embedding across profiles.** | The system deliberately refuses (1536-dim stored vs 1024-dim active). Padding or mixing would silently corrupt the HNSW index. The guard is working as designed. |
| **Two redaction tiers, not blanket deletion.** | `direct` (credentials, contact, government/financial IDs, precise location, health) → `[REDACTED]`. `soft` (person, org, city) → consistent pseudonym `[PERSON_1]` with given/surname backfill. Deleting names would destroy the entity graph; pseudonyms keep coreference without storing the real name. |
| **Response cache outside the rate limiter.** | A served-from-cache read must not consume the caller's quota. |
| **All Redis-backed controls fail open.** | A cache or limiter outage must degrade to uncached/unlimited, never to a failed request. |
| **Middlewares run last-added-outermost.** | Effective order is `Auth → Tenant → ResponseCache → RateLimit → GZip`. The cache and limiter sit *inside* auth because they need the resolved tenant. |

---

## 7. Known limitations and open items

Ordered by how much they matter.

**7.1 The 100% fine-tune score is not a generalisation result.** The split is
record-hashed, but the corpus is ~10 template families, so the model may have learned
templates rather than the task. A **template-family-held-out** split is the honest test
and has not been run. Treat 100% as "learned the contract", not "generalises".

**7.2 MCP is now hardened and verified — two residual gaps.** `contexta/mcp/security.py`
adds API-key auth, tenant scoping, `safe_local_path` (traversal/symlink confinement),
`safe_remote_fetch` (SSRF guard: https-only, DNS re-checked on every redirect,
private/loopback rejection, byte cap), a rate limiter, and content/importance validation.
The live check passes 4/4 and a probe write was confirmed to land in the injected
tenant with the PII redacted. Remaining:
- `tests/test_mcp_security.py` has 2 DB-backed tests that cannot run on the host (see the
  port note in section 4). They pass in-container.
- **MCP wrote its embedding to the wrong vector column.** It stored 1024 dims into
  `embedding` (which is 1536), which raised `EmbeddingDimensionError` — so every MCP
  write was failing outright, and had it been padded it would have been invisible to
  dense retrieval. Now writes `embedding_1024` plus profile metadata. **Worth grepping
  for other direct `MemoryRecord(...)` constructions that set `embedding=`.**

**7.3 `file_path` / `file_url` were sandboxed, not removed.** They remain available for
bulk import. If that workflow is not actually needed, deleting both parameters is
strictly safer and simpler.

**7.4 Extraction quality nit.** The model emits `preferences` where `prefers` reads
better, so a title reads "the user preferences dark mode". Fix in *training data*, not the
prompt — changing the inference prompt would break the tuned accuracy.

**7.5 MCP user identity is still a free-form string** (`to_uuid` coerces via uuid5), while
REST uses real UUIDs. An agent using both surfaces addresses the same person by two
different identifiers.

**7.6 Pre-existing lint debt** in files outside this workstream: `api/routes/system.py`
(3× BLE001, S110), `api/routes/audit.py` (F841), `api/routes/graph.py` (F841 unused
`link_repo`, C401), `models/` misc. Not introduced here.

**7.7 Idle but available:** the RTX 3060 sits at ~73 MiB / 6 GB with the model server on
CPU torch. Moving embedding/reranking to GPU is the largest untouched latency win
(measured `rerank x45` ≈ 1051 ms, `embed x1` ≈ 91 ms cold box).

**7.8 Repeated cold-path variance.** A cold `/v1/retrieve` was observed between 1.1 s
and 17.6 s across runs, caused by concurrent benchmark load. Ratios measured
back-to-back are trustworthy; absolute milliseconds are not. Measure on an idle box.

---

## 8. Next steps, in priority order

1. **Grep for other direct `MemoryRecord(...)` writes that set `embedding=`.** The MCP
   path wrote 1024-dim vectors into the 1536-dim `embedding` column, so every agent
   write was failing. Any remaining `embedding=` on a direct model construction is a
   latent instance of the same bug.
2. **Run a template-family-held-out** extraction eval to get a real generalisation number
   (7.1).
3. **Decide on MCP bulk import**: keep the sandboxed `file_path`/`file_url`, or remove
   them and force `POST /v1/artifacts`.
4. **Move the model server to the GPU**, then re-measure retrieval cold and warm.
5. **Split embedding and reranking** into separate processes; they currently contend.
6. **Adaptive rerank pool** — `RERANK_POOL_SIZE = 45` through a cross-encoder is
   expensive; rerank the top ~20 by RRF.
7. **Align the SDKs with the kernel contract** — both SDKs target `/v1/observations`;
   `/v1/kernel/observe` is the richer contract and remains unused by clients.
8. **Add a health assertion** so a `created` api/worker/beat fails loudly (3).
9. **Commit.** The tree has ~250 changed paths and no commit. The Go agent noted
   `list_policies` / `register_policy` / `register_schema` target routes that do not
   exist and need an API decision.

---

## 9. Map of the code that matters

| Path | What it does |
| --- | --- |
| `contexta/api/app.py` | Route mounting + middleware order. Read this first. |
| `contexta/api/middleware/response_cache.py` | Redis cache + single-flight. Tenant-keyed. |
| `contexta/api/middleware/ratelimit.py` | Per-key token bucket, tier-aware, fail-open. |
| `contexta/core/extraction/pii_filter.py` | Pure-code PII detection, two tiers, checksums. |
| `contexta/core/extraction/sensitive_filter.py` | `redact_all` / `primary_scan` / `secondary_redact`. |
| `contexta/contracts/extraction.py` | **Single source of truth** for the extraction contract. |
| `contexta/services/llm.py` | Extraction call path + heuristic last resort. |
| `contexta/repositories/ingestion_repo.py` | Durable outbox, leases, attempt numbering. |
| `contexta/workers/outbox_tasks.py` | Claim **and publish** (the signal was removed). |
| `contexta/workers/extraction_tasks.py` | Lease release, dead-letter, retry policy. |
| `contexta/mcp/security.py` | MCP auth, path/SSRF guards, rate limiting. |
| `contexta/mcp/service.py` | MCP tools. Tenant from the constructor; writes `embedding_1024`. |
| `services/gateway/` | Stateless edge only. Cache lives in Python, not here. |
| `benchmarks/api_smoke_test.py` | 25-endpoint contract check. Run after any API change. |
| `benchmarks/redaction/` | Redaction corpus, scorer, CSV/JSON/HTML reports. |
| `benchmarks/extract_e2e_test.py` | Proves an observation becomes a real memory. |
| `benchmarks/mcp_security_check.py` | Live MCP checks. **Run in-container** (see section 4). |
| `benchmarks/mint_mcp_key.py` | Regenerates the local `.env` MCP key. |
| `tests/test_mcp_security.py` | MCP unit tests (2 need a live DB). |

---

## 10. Conventions to follow

- **Never commit, reset, or clean** this worktree without being asked.
- Python: `uv run --no-sync`. Lint with `uv run --no-sync ruff check`. Do not add
  `noqa` to silence a real finding; justify it in a comment when the behaviour is
  intentional.
- Go: `gofmt -w` before finishing; `go build ./... && go vet ./...` must pass.
- Prefer Ruff-clean files over matching a file's pre-existing lint baseline — but say so
  when you change a file's lint count, so reviewers can tell deliberate cleanup from
  noise.
- Tests were written where they caught real bugs (middleware cache, Go single-flight).
  Add tests for new code in the same spirit: assert on the property that matters
  (tenant isolation, fail-open) rather than on the happy path only.

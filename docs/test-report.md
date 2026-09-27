# Contexta — Test & Quality Report

> **Superseded.** This report describes the tree as of August 8, 2026 and is kept for the record. For the current numbers see [AGENT-1-STATUS.md](AGENT-1-STATUS.md) and the focused gates in [`Featuers/quality-gates.md`](Featuers/quality-gates.md).

Generated: August 8, 2026 · Python 3.12 · Windows

## Summary at the time

| Metric | Result |
|---|---|
| Tests collected | **220** |
| Tests passing | **220 (100%)** |
| Tests failing | 0 |
| Suite runtime | ~6–8s (full suite, no coverage) |
| Overall coverage | **70%** (3,580 statements, 1,087 missed) |
| Ruff (Python) | **All checks passed** (0 errors) |

### Since then

| | Then | Now (v1.5) |
|---|---:|---:|
| Tests passing | 220 | **392** |
| Test files | 24 | 33 |

New suites include `test_temporal_normalization.py`, `test_ingestion_outbox.py`, `test_retrieval_fusion.py`, `test_structural_fact_key.py`, `test_graph_traverse_is_tenant_scoped.py`, `test_mcp_security.py`, `test_cortex.py`, `test_api_middleware.py`, `test_model_server_backpressure.py`, and `test_locomo_benchmark.py`.

## Suites that no longer exist

`test_schema_registry.py` and `test_policy_engine.py` were deleted along with the schema registry, the policy engine, semantic clustering, the compression engine, and the retrieval-feedback table. If you are reading a coverage row that names them, it is describing removed code.

## Bugs found & fixed during that run

1. **Celery/Redis hang in tests** — `.env` set `CONTEXTA_CELERY_TASK_ALWAYS_EAGER=false`, so API tests tried to reach a Redis broker and retried 20× (~10 min hangs). Fixed in `tests/conftest.py`: force eager mode + in-memory broker before imports.
2. **`extra_forbidden` crash on startup** — any variable in `.env` not declared in `Settings` (e.g., `DEEPSEEK_API_KEY`) crashed the API. Fixed: `extra="ignore"` in `contexta/config/settings.py`.
3. **Naive/aware datetime `TypeError`** in `importance.recency_modifier` and `engine.compute_freshness` — production crash path when mixed datetimes arrive. Fixed with UTC normalization.
4. **`datetime.utcnow()` deprecation sweep** — 9 core/services files migrated. (Persisted model defaults intentionally left; flagged for a timezone-aware column migration. This is still outstanding: `sessions.py`, `memory_repo.py`, and the model defaults still call it and emit `DeprecationWarning` on every run.)
5. **TS SDK never compiled** — unterminated template literal in `context.ts`. Fixed.
6. **TS SDK missing runtime types** — added ambient declarations for Node/Deno/Bun.
7. **Flaky hypothesis test** — payload property tests fixed with `deadline=None`.
8. **Ruff lint debt** — 314 pre-existing errors → 0.
9. **Dashboard lint** — removed unused `nodeById` in `entity-graph.tsx`. (That component has since been deleted too.)
10. **Stub cleanup** — `forgot-password` simplified to a generic response. Still flagged: the email flow is not implemented.

## Product-spec metrics (claims, not measured)

- Sub-100ms p99 retrieval at 1M memories per tenant — **spec claim, not measured.** No load-benchmark harness exists. Do not quote it.
- ~80% token savings via extraction — spec claim from business-plan estimates. The LoCoMo harness's own token total double-counts retrieved context, so it cannot substantiate this.
- 3-layer tenant isolation (repo scope + Postgres RLS + CI cross-tenant tests) — the repo-scope layer and the cross-tenant tests are real (`tests/test_graph_traverse_is_tenant_scoped.py`, `tests/test_mcp_security.py`). **Postgres RLS is not enabled**; isolation is enforced in application code by `TenantScopedRepository`.

## Running it, now

```bash
# From the repository root
uv run pytest tests/ -q
.venv\Scripts\python.exe -m pytest tests/ -q   # Windows venv

# Focused gate: temporal, durable ingestion, fusion, retrieval
uv run pytest tests/test_temporal_normalization.py tests/test_ingestion_outbox.py \
               tests/test_retrieval_fusion.py tests/test_retrieval_engine.py -q

# Tenant isolation
uv run pytest tests/test_graph_traverse_is_tenant_scoped.py tests/test_mcp_security.py -q

# Lint
uv run ruff check contexta tests

# Go gateway
cd services/gateway && go build ./... && go vet ./...

# Console
cd dashboard && bun run lint && bun run build
```

There is no `web/` or `web-public/` directory. The console is `dashboard/` and the public site is `landingpage/`, which is a **separate git repository** and is not built from this checkout.

# Contexta — Test & Quality Report

Generated: August 8, 2026 · Python 3.12 · Windows

## Summary

| Metric | Result |
|---|---|
| Tests collected | **220** |
| Tests passing | **220 (100%)** |
| Tests failing | 0 |
| Suite runtime | ~6–8s (full suite, no coverage) |
| Overall coverage | **70%** (3,580 statements, 1,087 missed) |
| Ruff (Python) | **All checks passed** (0 errors) |
| Dashboard lint/build (`web/`) | Passed, 0 warnings |
| Landing page lint (`web-public/`) | Passed, 0 warnings |
| Landing page typecheck + build | Passed (Next.js static prerender) |
| TypeScript SDK build (`clients/typescript/`) | Passed (ESM + CJS + DTS) |

## Test suites (24 files)

| Suite | Focus |
|---|---|
| test_sensitive_filter.py (401 lines) | Sensitive-data redaction at ingestion — passwords, API keys, JWTs, OTPs |
| test_memories_and_sessions_api.py (429 lines) | Memories lifecycle, context, explain API |
| test_observations_api.py | Observation ingestion, 1MB payload boundary, batches |
| test_truth_maintenance.py | Contradiction detection, supersession, versioning |
| test_retrieval_engine.py | Hybrid retrieval, graph expansion, scoring |
| test_entity_resolver.py / test_entity_state_manager.py | Entity resolution and state |
| test_deduplication.py | Fact deduplication |
| test_importance_framework.py / test_scoring_engine.py | Importance scoring, clamping |
| test_schema_registry.py / test_policy_engine.py | Schemas and policies |
| test_embedding_service.py | Embedding provider (deterministic mode) |
| test_extraction_worker.py | Async extraction pipeline |
| test_required_batch_12_24.py | Decay, reflection, compression, clustering, dream engines |
| test_property_payload_validation.py | Hypothesis property tests on payload boundaries |
| test_repositories.py / test_memory_storage.py | Persistence layer |
| test_api_keys.py / test_core_errors.py / test_core_schemas.py / test_core_types.py / test_property_payload_validation.py | Core contracts |

## Coverage highlights (by area)

| Area | Coverage |
|---|---|
| **Core engine** (extraction, truth, scoring, retrieval, entities, policy) | **84–98%** |
| Sensitive filter | 98% |
| Entities resolver | 95% |
| Policy engine | 94% |
| Deduplication | 94% |
| Truth maintenance | 92% |
| Observations API | 91% |
| Retrieval feedback | 90% |
| Context builder / planner | 85–88% |
| Sessions API | 98% |
| API keys API | 94% |
| Models layer | 100% |

Areas with low coverage (roadmap for future tests): workers (0–29% — Celery task bodies require a broker integration harness), migrations (0% — exercised by `alembic upgrade` in CI-deployed environments), `contexta/core/pipeline.py` (0%).

## Bugs found & fixed during this run

1. **Celery/Redis hang in tests** — `.env` set `CONTEXTA_CELERY_TASK_ALWAYS_EAGER=false`, so API tests tried to reach a Redis broker and retried 20× (~10 min hangs). Fixed in `tests/conftest.py`: force eager mode + in-memory broker before imports.
2. **`extra_forbidden` crash on startup** — any variable in `.env` not declared in `Settings` (e.g., `DEEPSEEK_API_KEY`) crashed the API. Fixed: `extra="ignore"` in `contexta/config/settings.py`.
3. **Naive/aware datetime `TypeError`** in `importance.recency_modifier` and `engine.compute_freshness` — production crash path when mixed datetimes arrive. Fixed with UTC normalization.
4. **`datetime.utcnow()` deprecation sweep** — 9 core/services files migrated to `datetime.now(timezone.utc)`. (Persisted model defaults intentionally left; flagged for a timezone-aware column migration.)
5. **TS SDK never compiled** — unterminated template literal (`sections.push(\`...\n"`) at `clients/typescript/src/context.ts:113` swallowed the rest of the file. Fixed.
6. **TS SDK missing runtime types** — added `src/env.d.ts` ambient declarations (Node/Deno/Bun) and `@types/node` for `fs`/`path`/`os` in `buffer.ts`.
7. **Flaky hypothesis test** — `test_payloads_within_1mb_*` failed intermittently with `DeadlineExceeded` (1MB payloads take 300–1500ms vs the 200ms default deadline under coverage). Fixed with `deadline=None` on both payload property tests.
8. **Ruff lint debt** — 314 pre-existing errors → 0. Configured idiomatic exceptions (FastAPI `Depends`, pydantic defaults, health-check failsafes), fixed real issues (unused vars, `raise exc` → `raise`, `logger.exception` misuse, blind `except` narrowing).
9. **Dashboard lint** — removed unused `nodeById` in `entity-graph.tsx`.
10. **Stub cleanup** — `forgot-password` created an unused JWT and never sent an email; simplified to the honest generic response (flagged: implement email flow before launch).

## Product-spec metrics (claims, not measured here)

- Sub-100ms p99 retrieval at 1M memories per tenant — spec claim (needs a load benchmark harness; flagged as roadmap).
- ~80% token savings via extraction — spec claim based on business plan estimates.
- 3-layer tenant isolation (repo scope + Postgres RLS + CI cross-tenant tests) — architecture claim; RLS enforcement tests flagged as roadmap.

## Running it

```
pip install -e ".[dev]"
python -m pytest                          # unit tests
python -m pytest --cov=contexta           # with coverage
ruff check contexta tests                 # lint
cd web && npm run lint && npm run build
cd web-public && npm run lint && npm run build
cd clients/typescript && npm run build
```

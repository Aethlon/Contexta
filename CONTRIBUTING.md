# Contributing to Contexta

Thanks for your interest in Contexta! Contexta is a memory layer for AI agents — it gives agents long-term memory through a simple API: call `observe()` to store what happened, and `context()` to retrieve what is relevant. This repo contains the engine, services, SDKs, and dashboards that make up the platform.

## Repository layout

| Directory | What lives here |
| --- | --- |
| `contexta/` | The Python engine and FastAPI backend |
| `services/gateway/` | The Go stateless edge gateway (TLS, API-key verification, rate limiting), profile-gated behind `edge` and off by default |
| `clients/` | Python and TypeScript SDKs |
| `dashboard/` | The Next.js operator dashboard |
| `landingpage/` | The public product site — a **separate git repository** (`Jenithpaul/contexta-landing`), not built by the compose stack |
| `docs/` | Documentation site and feature deep dives |
| `benchmarks/` | Reproducible evaluation harnesses and recorded results |
| `tests/` | Backend tests |

## What to contribute

We highly encourage contributions. Current focus areas are:

1. **Temporal correctness**: Preserve `occurred_at`, `observed_at`, timezone, precision, basis, and source provenance without inventing missing dates.
2. **Durable processing**: Keep ingestion idempotent, tenant-scoped, lease-safe, retryable, and observable through attempts and dead letters.
3. **Retrieval quality**: Treat weighted RRF across dense, lexical, and graph channels as the canonical ordering path.
4. **Operational clarity**: Keep queue routing, bounded work, retries, and backpressure behavior aligned with the documentation.
5. **Documentation and reproducibility**: Make claims traceable to source or recorded evidence, and keep benchmark caveats next to the numbers.

## Local development

### Option A: Docker

```bash
cp .env.example .env
docker compose up --build
```

### Option B: Python directly

```bash
pip install -e ".[dev]"
uvicorn contexta.api.app:app
```

You will also need PostgreSQL, pgvector, and Redis running. Apply the Alembic migrations before testing durable storage:

```bash
alembic upgrade head
```

## Tests and validated quality gates

Run the full backend suite before opening a pull request, from the repository root:

```bash
uv run pytest tests/ -q
# Windows venv:
.venv\Scripts\python.exe -m pytest tests/ -q
```

The focused gate for temporal grounding, durable ingestion, and canonical retrieval is:

```bash
uv run pytest tests/test_temporal_normalization.py tests/test_ingestion_outbox.py tests/test_retrieval_fusion.py tests/test_retrieval_engine.py -q
```

The current tree passes **392** tests overall and **58** in that focused gate. The focused gate verifies deterministic mechanics; it is not a LoCoMo accuracy threshold. See [`docs/Featuers/quality-gates.md`](docs/Featuers/quality-gates.md) for the behavior covered by each test.

Tenant-isolation regressions have their own files and are not optional reading before touching a query:

```bash
uv run pytest tests/test_graph_traverse_is_tenant_scoped.py tests/test_mcp_security.py -q
```

A `select()` against a tenant-owned model that does not go through `TenantScopedRepository` is treated as a security bug, not a style nit — see `AGENTS.md` invariant B.

## Linting and documentation checks

```bash
uv run ruff check contexta tests benchmarks/locomo/run_benchmark.py
cd docs
npm install
npm run lint
npm run build
cd ..
git diff --check
```

`docs/` is a Nextra 2 site on Next.js 14. Feature Markdown under `docs/Featuers/` is not compiled by Nextra, so review its links, tables, and code fences manually.

The repository has no Markdown linter configured.

## Benchmark reporting rules

- Treat `benchmarks/locomo/RESULTS.md` as a recorded baseline, not an enforced quality gate.
- Update the raw result artifact and formatted report from the same run; never invent a missing measurement.
- Record model, judge, retrieval, embedding, command, revision, and dataset provenance before making a comparative claim.
- Keep retrieval-only metrics separate from generated-answer accuracy.
- Preserve model-dependent judge limitations and token-accounting caveats.
- Do not present a partial, legacy, or differently configured run as proof of a current quality gate.

The public observation route now commits a tenant-scoped observation, source turns, and an outbox event before returning `202 Accepted`, then schedules durable processing by identifier. Changes to that path must preserve idempotency, authenticated tenant matching, status reporting, transaction boundaries, tenant-aware outbox recovery, and published-state convergence.

## Making a pull request

1. Fork the repository and create a feature branch.
2. Make your change, keeping it focused and well described.
3. Run the tests and linter before opening the PR.
4. Open a pull request describing what you changed and why.

## License

Contexta is licensed under a dual-licensing model:

* **Personal & Non-Commercial Use**: Apache License, Version 2.0. Free for individuals, hobbyists, non-commercial self-hosting, internal testing, evaluation, and development.
* **Commercial & Production Business Use**: a paid commercial licence is required for commercial entities, business environments, production enterprise deployments, and any use where Contexta is part of or powers a commercial product, platform, SaaS, or managed service. Contact `licensing@contexta.dev`.

Do not describe the project as flat "Apache 2.0". See [LICENSE](LICENSE) for the full terms.

# Quality Gates & Benchmark Evidence

Contexta's quality gates separate deterministic engineering correctness from model-dependent benchmark scores. A passing test gate does not turn a recorded benchmark run into a release threshold, and a benchmark score does not replace behavioral regression tests.

---

## 1. Focused Regression Gate

The temporal, durable-ingestion, and canonical-retrieval changes share this command:

```bash
uv run pytest tests/test_temporal_normalization.py tests/test_ingestion_outbox.py tests/test_retrieval_fusion.py tests/test_retrieval_engine.py -q
```

The current tree passes **58 of 58 tests**. The full backend suite is **392 passed, 0 failed, 0 skipped**. Pytest emits `DeprecationWarning` from `datetime.utcnow()` calls in `sessions.py`, `memory_repo.py`, and the model defaults; those are warnings, not failures, and are tracked separately.

### What the Gate Validates

| Area | Required behavior |
| --- | --- |
| Relative dates | Resolve supported expressions with an explicit reference and IANA timezone |
| Missing time | Preserve unresolved expressions instead of inventing a date |
| Temporal persistence | Derive event/observation time, precision, basis, and unknown fallback metadata |
| Durable idempotency | Scope keys by organization and reject changed payloads under the same key |
| Concurrency | Use PostgreSQL row locks with `SKIP LOCKED` and recover expired leases |
| Outbox safety | Return identifiers and lease tokens without leaking ORM objects through task results |
| RRF | Reward cross-channel agreement, de-duplicate each channel, and keep utility as a small prior |
| Lexical retrieval | Use parameterized `websearch_to_tsquery` and `ts_rank_cd` with tenant filters |
| Candidate bounds | Keep graph-only candidates, exclude unsupported filler, and cap the reranker pool |

This gate is a correctness check, not a claim about retrieval accuracy on LoCoMo.

---

## 1b. Tenant-Isolation Gate

Separate, and not optional before touching a query:

```bash
uv run pytest tests/test_graph_traverse_is_tenant_scoped.py tests/test_mcp_security.py -q
```

**31 passed.** This gate exists because v1.5 shipped three cross-tenant defects and fixed all three:

- `GET /v1/graph/traverse` resolved its root entity with an unscoped `Entity.name.ilike(...)`, so one tenant could read another tenant's entity names, entity summaries, memory titles, and memory body text — and a name shared across tenants returned a `500`.
- The MCP `get_metrics` tool used an unscoped `COUNT(*)`, leaking every tenant's row counts to every tenant.
- `contexta/scripts/enrich_graph.py` performed a cross-tenant `DELETE`.

A `select()` on a tenant-owned model that does not go through `TenantScopedRepository` is a security bug, not a style nit. A red run here is an incident, not a flaky test.

---

## 2. Full Validation

Before a broad change is merged, run the complete backend suite and Python lint:

```bash
uv run pytest tests/ -q
uv run ruff check contexta tests benchmarks/locomo/run_benchmark.py
```

The repository's current lint configuration applies to Python, not Markdown. The Go gateway has its own gate:

```bash
cd services/gateway && go build ./... && go vet ./...
```

The `docs/` site is a Nextra 2 application on Next.js 14. Note that `npm run build` currently **fails** because `docs/next.config.ts` is not a supported filename for Next 14 — rename it to `next.config.mjs`. That is a config issue, not a content issue.

The `docs/Featuers/` Markdown files are not compiled by the Nextra application, so reviewers should check links, tables, and rendered code fences manually.

---

## 3. LoCoMo Evidence Rules

The checked-in LoCoMo run is a recorded baseline, not an enforced numeric gate. The runner does not define a minimum accuracy, regression delta, category floor, or CI exit threshold.

Benchmark changes must meet all of these evidence rules:

1. Keep raw per-question records, aggregate results, configuration metadata, and `RESULTS.md` from the same run.
2. Record the command line, code revision, dataset checksum, migration head, generator model, judge mode and model, embedding backend, retrieval limit, and hardware.
3. Judge generated answers without exposing retrieved context to the judge; preserve adversarial abstention as an explicit requirement.
4. Keep retrieval-only diagnostics separate from end-to-end answer correctness.
5. Do not compare runs that use different generators, judges, context limits, retrieval limits, or ingestion paths as if they were controlled experiments.
6. Do not present a score as a release guarantee, competitor result, or latency claim unless the artifact measures that exact property.

### Current Artifact Limitations

- The checked-in raw JSON does not record all required provenance above.
- The top-level `retrieval_limit` is `15`, while per-question records report 20 retrieved memories and the current CLI default is 20.
- Generator prompt tokens already include the supplied context, while the report adds `context_tokens` again to its total. The reported total and 25,000-token arithmetic are not unique-token measurements.
- The token tracker records answer-generation calls, not every extraction, classification, reranking, or judge call.
- The benchmark-specific ingestion path does not exercise the durable HTTP acceptance/outbox path.
- Its temporal handling predates the new `event_at`/`observed_at` persistence path, so the temporal category is not a validation of that feature.

See [the benchmark methodology](../../benchmarks/locomo/README.md) and [recorded results](../../benchmarks/locomo/RESULTS.md) for the complete caveats.

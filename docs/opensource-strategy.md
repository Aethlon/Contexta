# Contexta — Open-Source & Licensing Strategy

> **Status note (v1.5).** Sections 1, 2, 5, and 6 still describe the current licensing and repository shape. Sections 3, 4, and 7 are kept for the record but describe an earlier plan: there is no hosted Contexta Cloud, and several of the feature flags and modules they cite have since been removed. Corrections are noted inline.

## 1. Decision

**Open-core, source-available repo with a dual license.**

Everything in the repository — the Python engine (`contexta/`), the Go edge (`services/gateway/`), the SDKs (`clients/`), the operator console (`dashboard/`), the documentation site (`docs/`), and the benchmarks (`benchmarks/`) — is public.

The public marketing site lives in `landingpage/`, which is a **separate git repository** (`https://github.com/Jenithpaul/contexta-landing.git`) and is not part of this checkout.

The license is dual (see `LICENSE`, the root `README.md`, and `/licensing` in the docs site):

| Use | License | Notes |
|---|---|---|
| Personal & self-use (individuals, hobbyists, non-commercial self-hosting, internal testing/eval/development) | **Apache 2.0** | Free |
| Any commercial / enterprise / SaaS use (powering a product, platform, or managed service) | **Paid Commercial License** | Contact `licensing@contexta.dev` |

## 2. Why Open

1. **Trust is the #1 purchase factor for a memory layer.** Developers store agent memories (user facts, preferences, sometimes sensitive data) in it. A memory layer they cannot inspect is a risk they won't take; a memory layer they *can* inspect is an asset they'll self-host.
2. **Distribution.** The repo is the top of the marketing funnel — the star count is a load-bearing metric.
3. **Framework adoption.** LangChain/LlamaIndex-ecosystem developers evaluate on GitHub; an inspectable engine beats a black box in every comparison table.
4. **Recruiting & docs quality.** Public code and docs act as the strongest engineering marketing we have.
5. **The moat is the commercial license, not hidden code.** What competitors can copy from a repo is commodity; a nine-stage pipeline with fail-closed redaction, structural fact keys, and schema-enforced truth maintenance is not.

## 3. What Stays Closed / Cloud-Only

> **Stale as of v1.5.** There is no hosted Contexta Cloud. Every feature listed below that was described as "cloud-only" now ships in the self-hosted default, and several of the modules named here have been deleted outright.

**The original position**, for the record: nightly reflection, the dream cycle, compression, and advanced clustering were proposed as hosted-only. What actually happened:

| Original claim | Reality in v1.5 |
|---|---|
| `feature_compression`, `feature_semantic_clustering`, `feature_retrieval_feedback` flags | **Removed.** The compression engine, clustering engine, and `retrieval_feedback` table are gone. Revision `020` dropped their schemas. |
| `feature_reflection_engine`, `feature_decay_engine` | **Removed as flags.** `contexta/core/reflection/engine.py` and `contexta/core/decay/engine.py` exist and run; the settings keys do not. |
| `feature_dream_cycle` (`False`) | The flag is still `False`, and `contexta/core/dream/engine.py` ships. Nothing gates it behind auth. |
| `feature_sensitive_data_filter` (`True`) | Still `True`, and now **fail-closed** rather than best-effort. |
| Cloud billing/metering internals (`contexta/services/dodo_billing.py`) | **Deleted.** Billing and metering are permanently excised; revision `020` dropped the 18 remaining billing tables. There is nothing to keep closed. |

What is still genuinely not in the repository:

- Production deployment topology details (single-tenant Node/Redis/worker splits, VPC peering).
- Enterprise SOC 2 controls documentation and audit materials (shared under NDA/BAA with commercial-license customers).
- The paid commercial license terms themselves.

## 4. What to Open Next (Release Checklist)

| Item | Status |
|---|---|
| `contexta-client` → PyPI, `@contexta/client` → npm | **Roadmap** — currently install-from-source (`clients/`) |
| Public benchmark report | **Shipped** — `benchmarks/locomo/README.md` and `RESULTS.md`, with caveats |
| CI workflow (`pytest` + lint) | **Present** — `.github/workflows/` |
| `CONTRIBUTING.md` | **Shipped** |
| `LICENSE` | **Shipped** — dual license, see `LICENSE` |
| Public roadmap / status notes | **Shipped** — `docs/AGENT-1-STATUS.md` |
| MCP server | **Shipped** — `contexta/mcp/`, 12 tools on `:8765` |
| Public benchmark *page* on the marketing site | **Shipped** — `landingpage/src/app/benchmarks/` (separate repo) |
| SPDX headers in source files | **Open** |

## 5. Guidelines for Contributors

- **Community PRs are welcome for personal / non-commercial use** (Apache 2.0 scope). Bug fixes, docs, examples (`clients/examples/`), tests, and performance work are always useful.
- **Commercial users need the paid license** — using Contexta to power a commercial product, SaaS, or enterprise deployment requires the Commercial License regardless of how code was obtained.
- Contributions are accepted under the Apache 2.0 terms (per Section 5 of the Apache License, as incorporated by `LICENSE`).
- Maintainers reserve the right to keep hosted-service code (if any is added later) out of the repo.
- License questions: `licensing@contexta.dev`.

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Competitors copy features from the repo | The hard parts are schema-level: `uq_memory_record_current_fact_slot`, the case-insensitive `entity` uniqueness constraint, the closed relationship-type CHECK, the bitemporal index. Rebuilding those is not a weekend job. |
| License enforcement overhead | Clear `LICENSE`, a `/licensing` docs page, and a single contact email (`licensing@contexta.dev`) |
| Open-core perception issues ("open-washing") | Keep the repo genuinely useful standalone — it is: the **full stack runs with `docker compose up --build`**, offline, with no paid API key. |
| A `select()` bypassing `TenantScopedRepository` | Treated as a security bug, not a style nit. v1.5 shipped three such defects (a cross-tenant read in `GET /v1/graph/traverse`, a cross-tenant `COUNT(*)` in MCP `get_metrics`, a cross-tenant `DELETE` in `enrich_graph.py`) and all three are fixed with regression tests. |

## 7. Metrics to Watch

> **Stale.** The self-host-versus-cloud signup split is no longer measurable — there is no hosted offering to sign up for.

| Metric | Why |
|---|---|
| GitHub stars | Funnel health |
| npm / PyPI downloads | SDK adoption beyond the repo (once published) |
| PRs from outside the org | Community health |
| Issue response time | Trust signal for commercial-license evaluators |
| Cross-tenant regression tests passing | The highest-signal health metric in this repo. A red `tests/test_graph_traverse_is_tenant_scoped.py` is a security incident, not a flaky test. |


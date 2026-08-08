# Contexta — Open-Source & Licensing Strategy

## 1. Decision

**Open-core, source-available repo with a dual license.**

Everything currently in the repository — the Python engine (`contexta/`), API, Go services (`services/`), SDKs (`clients/`), dashboard (`web/`), landing page (`web-public/`), and docs (`docs/`) — is public.

The license is dual (see `LICENSE` and `README.md`):

| Use | License | Notes |
|---|---|---|
| Personal & self-use (individuals, hobbyists, non-commercial self-hosting, internal testing/eval/development) | **Apache 2.0** | Free |
| Any commercial / enterprise / SaaS use (powering a product, platform, or managed service) | **Paid Commercial License** | Contact `licensing@contexta.dev` |

## 2. Why Open

1. **Trust is the #1 purchase factor for a memory layer.** Developers store agent memories (user facts, preferences, sometimes sensitive data) in it. A memory layer they cannot inspect is a risk they won't take; a memory layer they *can* inspect is an asset they'll self-host.
2. **Distribution.** Mem0's ~62k GitHub stars are evidence that OSS is the primary funnel in this category. The repo is the top of the marketing funnel — the star count is a load-bearing metric.
3. **Framework adoption.** LangChain/LlamaIndex-ecosystem developers evaluate on GitHub; an inspectable engine beats a black box in every comparison table.
4. **Recruiting & docs quality.** Public code and docs act as the strongest engineering marketing we have.
5. **The moat is the commercial license + hosted service, not hidden code.** What competitors can copy from a repo is commodity; the hosted-only features, compliance story, and service reliability are what customers pay for.

## 3. What Stays Closed / Cloud-Only

**Hosted Contexta Cloud** (contexta.dev): nightly reflection runs, the dream cycle, compression, and advanced clustering execute behind auth on our infrastructure, not in the self-host default.

The split is already half-built in code: `contexta/config/settings.py` ships feature flags with hosted-leaning features **off by default** in the open repo:

| Flag | Default |
|---|---|
| `feature_reflection_engine` | `True` |
| `feature_sensitive_data_filter` | `True` |
| `feature_compression` | `True` |
| `feature_semantic_clustering` | `True` |
| `feature_retrieval_feedback` | `True` |
| `feature_decay_engine` | `True` |
| `feature_dream_cycle` | **`False`** |

So reflection/compression/clustering run self-hosted; the dream cycle (and future hosted-only nightly cycles) are cloud-only by default.

Also closed:

- Production deployment topology details (single-tenant Node/Redis/worker splits, VPC peering).
- Cloud billing/metering internals (`contexta/services/dodo_billing.py` is open, but hosted metering/pricing policy is not).
- Enterprise SOC 2 controls documentation and audit materials (shared under NDA/BAA with Enterprise customers).

## 4. What to Open Next (Release Checklist)

| Item | Status |
|---|---|
| `contexta-client` → PyPI, `@contexta/client` → npm | **Roadmap** — currently local-only (`clients/`) |
| MCP server | **Roadmap** — not yet in repo |
| Public benchmark report (retrieval quality, latency) | **Roadmap** — see `market-analysis.md` |
| CI workflow (`pytest` + lint) | **Roadmap** — no `.github/workflows/ci.yml` in repo yet; add one and keep it green |
| `CONTRIBUTING.md` | **Roadmap** — not present |
| Clear `LICENSE` + license headers in files | **Shipped** — `LICENSE` exists; add SPDX headers as part of contributing guidance |
| Public roadmap / status notes in docs | Partially shipped — see `Business plan/14-roadmap-and-finances.md` (public at repo level today) |

## 5. Guidelines for Contributors

- **Community PRs are welcome for personal / non-commercial use** (Apache 2.0 scope). Bug fixes, docs, examples (`clients/examples/`), tests, and performance work are always useful.
- **Commercial users need the paid license** — using Contexta to power a commercial product, SaaS, or enterprise deployment requires the Commercial License regardless of how code was obtained (matches the license grant in `LICENSE`).
- Contributions are accepted under the Apache 2.0 terms (per Section 5 of the Apache License, as incorporated by `LICENSE`).
- Maintainers reserve the right to keep hosted-service code (if any is added later) out of the repo, and to run hosted-only features behind auth as described in Section 3.
- License questions: `licensing@contexta.dev`.

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Competitors copy features from the repo | Speed + hosted-only features (dream cycle, nightly reflection, managed clustering) + benchmark moat; copying a memory lifecycle engine is not a weekend job |
| License enforcement overhead | Clear license header on files, obvious `LICENSE`, a single contact email (`licensing@contexta.dev`), and commercial-license FAQ in README/docs |
| Open-core perception issues ("open-washing") | Keep the repo genuinely useful standalone — it is: the **full stack runs with `docker compose up --build`** (deterministic local embedding provider, no paid API key required, per `README.md`) |
| Contributions violating license scope | Contributor guidelines (Section 5) + CLA-by-license-terms approach in CONTRIBUTING (roadmap) |

## 7. Metrics to Watch

| Metric | Why |
|---|---|
| GitHub stars | Funnel health; benchmark against Mem0 (~62k) |
| npm / PyPI downloads | SDK adoption beyond the repo |
| Discord/community size | Support cost, early-warning for docs/UX issues |
| PRs from outside the org | Community health (goal: >10% of merged PRs external within 6 months) |
| Issue response time | Trust signal for enterprise buyers evaluating the repo |
| % of signups choosing self-host vs cloud | Prices the hosted service, informs the Free-tier limits and Enterprise motion |

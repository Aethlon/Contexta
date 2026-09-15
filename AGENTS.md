# AGENTS.md — Agent & Contributor Playbook for Contexta

Welcome to the Contexta monorepo. This guide defines the system architecture, development conventions, critical invariants, and testing standards for autonomous AI coding agents and human engineers.

---

## 1. Monorepo Map & Component Boundaries

| Directory | Stack / Framework | Responsibility |
| :--- | :--- | :--- |
| `contexta/` | Python 3.11+, FastAPI, SQLAlchemy, Celery | **The Brain**: Orchestrates extraction, scoring, truth maintenance, entity resolution, and hybrid retrieval. |
| `services/` | Go 1.22+ | **The Data-Plane**: High-throughput ingress (:8443) and fast retrieval gateway (:8080). |
| `dashboard/` | Next.js 15, React 19, TailwindCSS, NextAuth v5 | **The Operator Console**: Memory inspector, entity graph viewer, API key manager, and live observation ingest. |
| `landing/` | Vite, React 19, TailwindCSS v4, MDX | **The Public Showcase**: Standalone open-source landing page and documentation viewer. |
| `docs/` | Nextra, Next.js, MDX | **Developer Documentation**: Public guides, quickstarts, API specifications, and architectural plans. |
| `clients/` | Python (`clients/python`) & TypeScript (`clients/typescript`) | **Agent SDKs**: Lightweight client libraries (`contexta.observe()`, `contexta.context()`). |
| `workers/` | Python Celery & Standalone Model Server | Async dream cycles, background embeddings, and micro-batched Qwen3 model server (:8001). |

---

## 2. Core Architectural Invariants

### A. Sovereign, Offline-First Default
* The system must boot and run completely offline without external cloud API keys using local Qwen3 models:
  * Embedding: `Qwen/Qwen3-Embedding-0.6B` (1024 dimensions)
  * Reranker: `Qwen/Qwen3-Reranker-0.6B`
* The model server runs on port `8001` (`workers/model_server.py`). Online mode (`BYOK` OpenAI/Anthropic/DeepSeek) is strictly opt-in via compose profiles or environment variables (`CONTEXTA_ENGINE_MODE=online`).

### B. Strict Multi-Tenancy Isolation
* **Zero Missing WHERE Clauses**: Every database interaction involving business entities must inherit from `TenantScopedRepository` (`contexta/repositories/base.py`).
* All queries are automatically scoped by `organization_id`. Never bypass repository tenant filtering in API routes.

### C. Ingestion Redaction & Truth Maintenance
* **Secrets Never Enter Memory**: Ingestion runs regex sanitization in `contexta/core/filter.py` before extraction to redact API keys, JWTs, bearer tokens, and passwords.
* **No Vector Accumulation Contradictions**: When a new observation updates or contradicts an existing memory, the truth engine (`contexta/core/truth/maintenance.py`) must invalidate the old record (`valid_to = now()`) and link the lineage via `MemoryVersion.superseded_by_id`. Stale facts are excluded from active retrieval.

### D. Hybrid 3-Layer Retrieval
* High-salience recall fuses:
  1. Dense vector cosine similarity via pgvector HNSW.
  2. Lexical keyword matching via PostgreSQL TSVECTOR GIN index (BM25).
  3. Multi-hop knowledge graph traversal via entity relationship edges.
* Candidates are merged via Reciprocal Rank Fusion (RRF) and scored by the neural reranker.
* Every retrieved memory hit must trigger read-age decay updates via `touch_accessed()`.

### E. No Billing or Metering Code
* Billing and usage metering have been permanently excised from Contexta Core. Do not re-introduce Stripe/Dodo checkout, billing webhooks, or credit deduction middleware.

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
# Run test suites:
pytest tests/ -v

# Run targeted suites:
pytest tests/test_retrieval_engine.py tests/test_api_keys.py -v
```

### Go Services (`services/`):
```bash
cd services/gateway && go build ./...
cd services/data-plane && go build ./...
```

---

## 4. Key Directory & Model Conventions

1. **API Routes**:
   * Stored in `contexta/api/routes/`.
   * Mounted in `contexta/api/app.py`.
   * Always accept `x-organization-id` / tenant context header.

2. **Dashboard Server Actions**:
   * Stored in `dashboard/src/app/actions.ts`.
   * Always use `contextaFetch()` from `@/lib/auth-helpers` to automatically attach session credentials and organization headers.

3. **Vector Dimension Rule**:
   * Offline Qwen3 = 1024 dimensions.
   * Online OpenAI = 1536 dimensions.
   * Do not mix dimensions without running a pgvector column migration or re-creating the database volume (`docker compose down -v`).

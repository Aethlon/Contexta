<p align="center">
  <img src="assets/logo.png" alt="Contexta Logo" width="620"/>
</p>

<h3 align="center">The Open-Source Long-Term Memory Engine for AI Agents</h3>

<p align="center">
  <strong>Give your agents memory that survives the session, corrects itself, and never leaves your machine.</strong><br/>
  Self-hosted • Offline-first • No per-call API fees • Strictly multi-tenant
</p>

<p align="center">
  <a href="#-the-nine-stage-pipeline">Pipeline</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-quickstart">Quickstart</a> •
  <a href="#-sdks">SDKs</a> •
  <a href="#-api-authentication">Auth</a> •
  <a href="#-running-the-tests">Tests</a> •
  <a href="docs/">Docs</a>
</p>

---

## 💡 What is Contexta

Contexta is a **memory layer for agents**. You hand it conversation turns; it extracts discrete, typed facts, links them into a knowledge graph, embeds them locally, and later hands back a token-budgeted slice of everything relevant to the current question.

It is not a vector store with a prompt bolted on. A naive memory layer quietly goes wrong in nine specific ways, and Contexta has a stage for each of them.

Two properties matter more than the retrieval quality:

- **It runs offline.** Embedding and reranking are local Qwen3 models. No cloud API key is needed to boot or to work.
- **It corrects itself.** When a user says *"I moved from New York to London"*, the old location is closed (`valid_to = now()`) and linked to its replacement. The system does not accumulate two contradictory vectors and hope the ranker sorts it out.

Everything persists in PostgreSQL + pgvector, which you own.

---

## 🧬 The Nine-Stage Pipeline

Every observation walks the same nine stages, in `contexta/core/pipeline.py` and the workers it enqueues. The *why* column is the part that matters — each stage exists because omitting it produces a specific, hard-to-debug failure.

| # | Stage | What runs | Why it exists |
| :-- | :--- | :--- | :--- |
| 1 | **Ingest** | `POST /v1/observations` persists a tenant-scoped observation, its ordered source turns, and a durable outbox event, then returns `202` | An in-memory queue loses observations on restart. The outbox claims rows with `SKIP LOCKED`, so concurrent workers never double-process and a crashed claim is retried rather than dropped. |
| 2 | **Redact** | `contexta/core/extraction/sensitive_filter.py` scrubs API keys, JWTs, bearer tokens, passwords, OTPs, session cookies, and card numbers | Secrets must never reach the extractor, the LLM, or the database. The gate is **fail-closed**: if it errors, the observation is rejected rather than forwarded unredacted. |
| 3 | **Extract** | The fine-tuned extractor on `:8002` returns discrete facts with a type, confidence, and explicit temporal precision | Free-form conversation is not memory. A typed fact with a provenance timestamp is something you can supersede later; a paragraph is not. |
| 4 | **Dedup** | Near-duplicate merge within the batch and against existing rows | Two phrasings of one fact become two rows, two vectors, and two chances to rank each other. A `subject`/`predicate`/`object` triple also yields a structural slot key `sfx1:<sha256>`, so a rephrasing lands in the *same* slot. |
| 5 | **Score** | Importance from emphasis, decision impact, and mention count; confidence from source type | A low-value extraction should be dropped *before* it costs an embedding and a graph edge. Ranking everything equally is how a memory layer turns into a noise store. |
| 6 | **Graph** | `BulkEntityResolver` resolves entities and typed edges in memory, then writes them | A fact is often reachable only through the people and projects around it. "What did the Fatima Okafor project ship?" needs the edge, not a better embedding. |
| 7 | **Reconcile** | `TruthSupersessionService` closes the contradicted row and records lineage via `memory_version.superseded_by_id` | This is the stage that makes memory *true* rather than merely accumulated. `uq_memory_record_current_fact_slot` — a partial unique index over `(organization_id, user_id, fact_key)` restricted to `valid_to IS NULL` — means a correction **must** supersede; it cannot coexist. |
| 8 | **Embed** | Local `Qwen/Qwen3-Embedding-0.6B` produces a 1024-dimension vector on your hardware | Retrieval needs vectors, and sending user text to a third party to get them defeats the point of self-hosting. 1024 dimensions is the offline column; do not mix it with the 1536-d online profile without a column migration. |
| 9 | **Retrieve** | Dense + lexical + graph evidence fuse via weighted RRF, then read-age decay is applied to every hit | One channel is never enough. Vectors miss exact tokens like port numbers; lexical misses paraphrase; the graph misses anything unlinked. Fusing all three and then *touching* each hit keeps decay honest by read-age rather than write-age. |

### Retrieval, in detail

| Channel | Engine | Default weight |
| :--- | :--- | ---: |
| Dense vector | pgvector HNSW, cosine | 0.5 |
| Lexical | PostgreSQL `tsvector` GIN / BM25 | 0.3 |
| Graph | recursive CTE, multi-hop, hard-capped | 0.2 |

Fusion is weighted Reciprocal Rank Fusion with `k = 60` (`contexta/core/retrieval/fusion.py`), plus a small quality prior from `importance`/`confidence`.

**Cascade mode exists but is off.** `RetrievalEngine(enable_dense_escalation=True)` inverts the order: lexical and graph gather evidence first, and `assess_primary_sufficiency()` decides whether the dense channel is needed at all. There is no environment variable and no request field for it — the constructor argument is the only switch. It stays off until the escalation rate is measured.

---

## 🏗 Architecture

| Directory | Language / stack | What it is |
| :--- | :--- | :--- |
| `contexta/` | Python 3.11+, FastAPI, SQLAlchemy, Celery | **The brain.** Extraction, scoring, entity resolution, truth maintenance, and retrieval. The only component that touches the database. |
| `contexta/workers/` | Python, Celery + FastAPI | Extraction, embedding, maintenance, and outbox queues; the local Qwen3 model server on `:8001` and the fine-tuned inference server on `:8002`. |
| `contexta/api/routes/` | Python, FastAPI | The HTTP surface. Mounted in `contexta/api/app.py`. |
| `contexta/mcp/` | Python, MCP | Model Context Protocol server on `:8765` (SSE) for Cursor, Windsurf, and Claude Desktop. |
| `services/gateway/` | Go 1.22 | **Optional.** TLS termination on `:8443` and Redis-backed key verification. Profile-gated behind `edge` and **off by default** — the response cache and per-key rate limiting it used to provide now live in the Python API. |
| `dashboard/` | Next.js 15, React 19, TailwindCSS 4 | The operator console: memory inspector, entity graph, API key manager. |
| `clients/python` | Python, httpx | `contexta-client` SDK. |
| `clients/typescript` | TypeScript, native `fetch` | `@contexta/client` SDK. |
| `docs/` | Nextra 2, Next.js 14, MDX | The documentation site. |
| `landingpage/` | Next.js App Router | The public product site. **A separate git repository** (`Jenithpaul/contexta-landing`) — not part of this compose stack. |
| `benchmarks/` | Python | LoCoMo and LongMemEval harnesses plus recorded results. |
| `tests/` | pytest | The backend suite. |

### Ports

| Port | Service |
| ---: | :--- |
| 3000 | Operator dashboard (falls back to 3001 if 3000 is taken) |
| 8000 | Contexta API |
| 8001 | Local Qwen3 model server (embedding + reranker) |
| 8002 | Fine-tuned extraction inference server |
| 8443 | Go gateway — only with `--profile edge` |
| 8765 | MCP server (SSE at `/sse`) |
| 5432 / 6379 | PostgreSQL (pgvector) / Redis |

---

## ⚡ Quickstart

### Prerequisites

Docker with Compose v2. Nothing else — no Python, no Node, no model API key. The first boot downloads the Qwen3 weights into `./models`, so give it a few minutes.

### 1. Bring the stack up

**macOS / Linux (or WSL / Git Bash):**

```bash
git clone <your-fork-or-clone-url> contexta
cd contexta
./entrypoint.sh
```

**Windows (PowerShell):**

```powershell
git clone <your-fork-or-clone-url> contexta
cd contexta
.\start.ps1
```

Either script copies `.env.example` to `.env` on first run, generates a self-signed certificate for the optional gateway, and starts the stack in the background.

Other entrypoint commands — `dev` (foreground, live logs), `stop`, `restart`, `status`, `logs`, `online`, `enterprise`, `models` (pre-download weights), `help`. `start.ps1` takes the same set except `models`.

**Or drive Compose yourself:**

```bash
cp .env.example .env          # Windows: Copy-Item .env.example .env
docker compose up --build
```

Verify:

```bash
curl http://localhost:8000/healthz      # {"status":"ok","version":"0.1.0"}
curl http://localhost:8000/readyz       # {"db":"ok","redis":"ok"}
```

Both endpoints are public and need no credentials.

### 2. Create your first API key

`POST /v1/keys` is itself authenticated, so the very first key has to be bootstrapped directly. The token is `mk_live_<url-safe>`, stored only as a SHA-256 hash, with the first 16 characters kept as a display prefix.

```bash
# macOS / Linux
docker compose exec -T postgres psql -U postgres -d contexta -c "
INSERT INTO api_key (id, name, prefix, token_hash, organization_id, actor_id, scopes, created_at)
VALUES (
  gen_random_uuid(),
  'first-key',
  'mk_live_LOCAL0',
  '<sha256 of your token>',
  '<organization uuid>',
  '<actor uuid>',
  ARRAY['read','write'],
  now()
);"
```

Generate the values first:

```bash
python -c "import hashlib,secrets,uuid;t='mk_live_'+secrets.token_urlsafe(32);print('TOKEN =',t);print('HASH  =',hashlib.sha256(t.encode()).hexdigest());print('ORG   =',uuid.uuid4());print('ACTOR =',uuid.uuid4())"
```

**Keep the actor UUID.** Every request's `user_id` must equal the authenticated actor, so a mismatch is a `403`, not a silent empty result. One key = one (organization, actor) pair.

Once you have a key, put it in `.env` so the containerised console can use it:

```bash
CONTEXTA_DASHBOARD_AUTH=off
CONTEXTA_DASHBOARD_API_KEY=mk_live_...
```

Open <http://localhost:3000> and the console resolves its tenant from that key. Use **API Keys** in the console to mint further keys for your applications.

> **The console ships without a sign-in.** `CONTEXTA_DASHBOARD_AUTH` defaults to `off` because Contexta is a self-hosted, single-operator tool. Set it to `on` to restore the NextAuth v5 credentials flow.
>
> **With auth off, do not expose the dashboard to an untrusted network.** Anyone who can reach `:3000` acts as whatever tenant it resolved.

### 3. Send your first observation

```bash
curl -X POST http://localhost:8000/v1/observations \
  -H "Authorization: Bearer $CONTEXTA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "'$CONTEXTA_ACTOR_ID'",
    "organization_id": "'$CONTEXTA_ORG_ID'",
    "session_id": "33333333-3333-4333-8333-333333333333",
    "messages": [
      {"role": "user", "content": "I moved from New York to London last month."},
      {"role": "assistant", "content": "Noted."}
    ]
  }'
```

`202 Accepted` comes back immediately with a `job_id`. Extraction is asynchronous. Poll it:

```bash
curl http://localhost:8000/v1/observations/$JOB_ID -H "Authorization: Bearer $CONTEXTA_API_KEY"
# {"status":"completed","attempt_count":1,"outbox_status":"published",...}
```

### 4. Read it back

```bash
curl -X POST http://localhost:8000/v1/retrieve \
  -H "Authorization: Bearer $CONTEXTA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"'$CONTEXTA_ACTOR_ID'","organization_id":"'$CONTEXTA_ORG_ID'",
       "query_text":"where does the user live","limit":5}'
```

---

## 🔒 The Offline-First Guarantee

The default stack needs **no external API key and no outbound network call** to do its job.

- Embedding: `Qwen/Qwen3-Embedding-0.6B`, **1024 dimensions**, served by `contexta/workers/model_server.py` on `:8001`.
- Reranking: `Qwen/Qwen3-Reranker-0.6B`, same server.
- `CONTEXTA_ENGINE_MODE=offline` is what compose sets, with `CONTEXTA_LLM_API_KEY` and `CONTEXTA_EMBEDDING_API_KEY` explicitly empty.
- `GET /v1/system/engine-status` tells you what is actually loaded. On a healthy offline install it reports `current_mode: "offline"`, `active_engine: "local_qwen"`, and `local_model_server.status: "healthy"`.

Online BYOK mode (OpenAI / DeepSeek / Anthropic) is opt-in via `./entrypoint.sh online` or `CONTEXTA_ENGINE_MODE=online`. **The online embedding profile is 1536 dimensions.** Switching between the two needs a pgvector column migration or a volume reset — do not pad or truncate vectors to fake it.

`docker-compose.yml` also ships a `deterministic` embedding profile, which is hash-derived rather than semantic. It exists to bring a stack up without a GPU; it is not a retrieval-quality baseline and no benchmark number in this repo was produced with it.

---

## 📦 SDKs

Both SDKs are in-repo and installable from source. `Contexta` / `AsyncContexta` are the canonical class names; the older lowercase `contexta` / `Asynccontexta` still import and work but emit a deprecation warning.

### Python

```bash
pip install -e clients/python
```

```python
from contexta_client import Contexta

# Reads CONTEXTA_API_KEY, CONTEXTA_API_URL, CONTEXTA_ORGANIZATION_ID
with Contexta.from_env() as memory:
    user_id = "<your actor uuid>"
    session_id = "33333333-3333-4333-8333-333333333333"

    memory.observe(
        user_id=user_id,
        session_id=session_id,
        messages=[
            {"role": "user", "content": "I prefer Postgres over Mongo for relational data."},
        ],
    )

    ctx = memory.context(
        user_id=user_id,
        session_id=session_id,
        token_budget=1500,
    )

    system_prompt = ctx.to_system_prompt()
```

`context()` and `create_session()` both require an organization id, because the server rejects a mismatch against the organization bound to your key.

Async mirrors it:

```python
from contexta_client import AsyncContexta

async with AsyncContexta.from_env() as memory:
    ctx = await memory.context(user_id=user_id, session_id=session_id, token_budget=1500)
    return ctx.to_system_prompt()
```

### TypeScript

```bash
npm install ./clients/typescript
```

```typescript
import { Contexta } from "@contexta/client";

const memory = Contexta.fromEnv();

try {
  const { jobId } = await memory.observe({
    userId: userId,
    sessionId: sessionId,
    messages: [
      { role: "user", content: "My name is Alice and I build in TypeScript." },
    ],
  });

  const { results } = await memory.retrieve({
    userId: userId,
    organizationId: organizationId,
    queryText: "What is my name?",
  });

  const ctx = await memory.context({ userId, organizationId, sessionId });
  console.log(ctx.toSystemPrompt());
} finally {
  memory.close();
}
```

Runs on Node 18+, Bun, Deno, Vercel Edge, and Cloudflare Workers. Zero required dependencies — native `fetch`, `crypto`, and `AbortSignal.timeout`.

Both clients send an `Idempotency-Key` on writes, retry `429`/`5xx`/network failures with backoff, and fall back to a durable on-disk queue when the network is down. `flush()` drains it, `close()` releases connections.

The two SDKs expose the same 32 public methods, asserted against `clients/public-api.manifest.json` by both test suites.

### Known SDK gaps in v1.5

Some client and CLI methods still call endpoints that no longer exist and will return `404` against a v1.5 server: policy and schema registration, project listing, `keys rotate`, and `usage`. They are listed in [`docs/src/app/reference/cli.mdx`](docs/src/app/reference/cli.mdx) so you are not surprised.

---

## 🔑 API Authentication

One API key carries **both** the organization and the actor. You do not need identity headers.

**Public — no headers required:**

```
/healthz  /readyz  /metrics  /docs  /redoc  /openapi.json
/v1/auth/signup  /v1/auth/signin  /v1/auth/reset-password
/v1/auth/emergency-wipe-reset  /v1/auth/onboarding
/v1/auth/verify-email  /v1/auth/forgot-password
```

**Everything else needs a key**, via either header:

```bash
Authorization: Bearer mk_live_...
# or
x-api-key: mk_live_...
```

**Identity headers are optional cross-checks**, not authentication. If you send them, they must agree with the key or you get a `403`:

| Condition | Response |
| :--- | :--- |
| `x-organization-id` (or `x-org-id`, `X-Mem-Tenant-Id`) disagrees with the key | `403 organization_mismatch` |
| `x-user-id` (or `x-contexta-user-id`, `X-Mem-Actor-Id`) disagrees with the key | `403 actor_mismatch` |
| An identity header is present but not a UUID, or two aliases disagree | `400 invalid_identity_header` |
| Legacy headers only, with `CONTEXTA_ALLOW_LEGACY_TENANT_HEADERS` unset | `401 authentication_required` |
| No key, no headers | `401 authentication_required` |
| Unknown or revoked key | `401 invalid_api_key` |
| Database or OS failure during key lookup | `503 authentication_unavailable` |

Legacy header-only authentication (`x-organization-id` + `x-user-id` with no key) is honoured **only** when `CONTEXTA_ALLOW_LEGACY_TENANT_HEADERS` is truthy. It is off by default.

The full contract, including per-endpoint parameters and the deliberate graph-route status changes, is in [`docs/src/app/reference/api.mdx`](docs/src/app/reference/api.mdx).

---

## 🧪 Running the Tests

From the repository root:

```bash
uv run pytest tests/ -q
```

On Windows with the checked-in virtualenv:

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

Current result: **392 passed, 0 failed, 0 skipped.**

The focused gate for temporal grounding, durable ingestion, and canonical retrieval:

```bash
uv run pytest tests/test_temporal_normalization.py tests/test_ingestion_outbox.py \
               tests/test_retrieval_fusion.py tests/test_retrieval_engine.py -q
# 58 passed
```

Tenant-isolation regressions — read these before touching any query:

```bash
uv run pytest tests/test_graph_traverse_is_tenant_scoped.py tests/test_mcp_security.py -q
# 31 passed
```

Lint and build:

```bash
uv run ruff check contexta tests
cd services/gateway && go build ./... && go vet ./...
```

### A note on the version string

`pyproject.toml` still declares `version = "0.1.0"`, and `GET /healthz` reports `"version": "0.1.0"`. This release is documented as **v1.5**. The version string is intentionally left alone here; treat the mismatch as a known packaging issue rather than evidence that you installed the wrong thing.

---

## 🏆 LoCoMo Snapshot

Contexta has been evaluated against [LoCoMo](https://github.com/snap-research/locomo) (Snap Research): 10 synthetic multi-session conversations, 1,986 answerable and adversarial questions. The recorded run uses real PostgreSQL + pgvector persistence, Contexta's extraction/deduplication/scoring/entity components, `RetrievalEngine.retrieve()`, `gemma3:1b` answer generation, and answer-only evaluation that does not expose retrieved context to the judge.

| Metric | Recorded run |
| :--- | ---: |
| Conversations | 10 |
| Questions scored | 1,986 |
| Overall answer correctness | **78.6%** |
| Adversarial abstention correctness | **92.8%** |
| Sessions ingested | 272 |
| Extraction failures | 0 |

| Category | Questions | Accuracy |
| :--- | :---: | :---: |
| Single-hop factoid | 282 | 68.4% |
| Temporal | 321 | 65.4% |
| Multi-hop reasoning | 96 | 69.8% |
| Open-domain recall | 841 | 80.5% |
| Adversarial distractors | 446 | 92.8% |
| **Overall** | **1,986** | **78.6%** |

**Read this before quoting it.** It is a recorded, model-dependent baseline — not an enforced release threshold, and not a controlled comparison against another memory system. It predates the v1.5 temporal-provenance and indexing work, the benchmark ingestion path does not exercise the public durable outbox, and the harness's own token total double-counts retrieved context, so no token-savings claim is derived from it.

Methodology and limitations: [`benchmarks/locomo/README.md`](benchmarks/locomo/README.md) and [`benchmarks/locomo/RESULTS.md`](benchmarks/locomo/RESULTS.md).

### Measured v1.5 engineering numbers

These are component-level measurements, not end-to-end accuracy:

| Path | Before | After |
| :--- | ---: | ---: |
| Lexical GIN search | ~550ms | ~48ms |
| `as_of` bitemporal read | ~46ms | ~0.22ms |
| Recursive-CTE graph traversal | ~38.5ms | ~2.16ms (~16x) |
| Session-level extraction success | ~17% | 87.5% |
| Public tables | 57 | 33 |

---

## 📚 Where to Go Next

| Resource | What it covers |
| :--- | :--- |
| [Developer docs (`docs/`)](docs/) | Quickstart, concepts, integration guides, full API and SDK reference, changelog, upgrade guide |
| [`AGENTS.md`](AGENTS.md) | Architectural invariants, component boundaries, v1.5 current state, testing standards |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Repository layout, quality gates, benchmark reporting rules |
| [v1.5 changelog](docs/src/app/changelog/page.mdx) | Added / Changed / Fixed / Performance / Removed, plus upgrade notes |
| [v1.5 upgrade guide](docs/src/app/reference/upgrade-v1.5.mdx) | Revisions 015-020 and what they require from you |
| [MCP server (`contexta/mcp/`)](contexta/mcp/) | Wiring Contexta into Cursor, Windsurf, and Claude Desktop |

---

## 📜 License

Contexta is **dual-licensed**, not flat Apache 2.0.

- **Apache License 2.0** covers individuals, hobbyists, non-commercial self-hosting, and internal testing, evaluation, or development.
- **A paid commercial license** is required for commercial entities, business environments, production enterprise deployments, or any use where Contexta is part of — or powers — a commercial product, platform, SaaS, or managed service. Contact **licensing@contexta.dev**.

See [LICENSE](LICENSE) for the full terms.

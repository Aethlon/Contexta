# CHIMERA — Contexta Hard Integrated Memory Evaluation & Reasoning Assay

CHIMERA measures **Contexta's** ability to do memory, not just to find text.
Every question requires simulating state changes across a stored history rather
than locating a passage. A good embedding model plus a reranker cannot pass it
without real consolidation, contradiction handling, temporal reasoning and
cross-domain fusion.

The harness is a *measuring instrument only*. It never re-implements, stubs or
patches Contexta logic.

---

## Architecture

```
generator.py            ground truth first, then questions + source material
      │
      ▼
data/questions.jsonl    THE EDITABLE QUESTION BANK  ◄── edit this freely
data/corpus.jsonl       ingestible source material
data/world.json         full ground truth (audit reference, never scored)
      │
      ▼
┌─ CONTEXTA (the system under test) ────────────────────────────────┐
│  MemoryPipeline.process_observation()   ← production ingestion    │
│    cortex → extraction → dedup → truth maintenance → persist     │
│    → entity resolution → embedding                              │
│                                                                   │
│  RetrievalEngine.retrieve()             ← production retrieval    │
│    dense + lexical + graph → weighted RRF → scoring → rerank     │
│  EmbeddingService                       ← production profile     │
└───────────────────────────────────────────────────────────────────┘
      │                                    │
      ▼                                    ▼
Gemma3:1b answers from context     retrieve_ms measured here
(the "application" layer)
      │
      ▼
score_answer()  →  PASS if it matches the reference answer
```

Only the **answering** step is external. Contexta is a memory layer and does not
generate answers, so a small local model plays the role of the calling
application — the same division of labour as `benchmarks/locomo`.

---

## What gets logged

Every run writes a complete audit trail, so each verdict can be traced end to end.

`results/chimera_<tag>.jsonl` — one record per question:

| Field | What it shows |
|---|---|
| `question` | the exact question asked |
| `reference_answer` | the gold answer |
| `reference_context` | the ground-truth facts + commits + distractors that *should* have been recoverable |
| `context_given_to_agent` | what Contexta actually retrieved, with per-channel scores (semantic / keyword / graph / recency / importance) |
| `context_given_to_agent_text` | the literal text handed to the model |
| `agent_answer` | what Gemma3:1b said |
| `verdict` / `verdict_reason` / `verdict_flags` | PASS/FAIL, why, and flags (`hallucinated`, `abstained`, `leaked`, `partial`) |
| `timing_ms` | `retrieve`, `answer`, `total` |
| `tokens` | prompt / completion token counts |
| `errors` | retrieval or answering errors, per stage |

`results/chimera_<tag>.ingest.json` — **what was saved in the DB while
extracting**: per-session extracted/stored/skipped counts, ingest timings, and
the full list of memory rows Contexta persisted.

`results/chimera_<tag>.summary.json` — accuracy, per-category breakdown, and
retrieval latency percentiles.

`results/chimera_<tag>.html` — the browsable report (see below).

---

## Setup

### 1. Isolated database (recommended)

CHIMERA should not share a database with other benchmarks — leftover rows skew
results. A dedicated Postgres with pgvector:

```powershell
docker run -d --name chimera-postgres `
  -e POSTGRES_PASSWORD=chimera -e POSTGRES_DB=chimera `
  -p 55433:5432 pgvector/pgvector:pg16

$env:CONTEXTA_DATABASE_URL='postgresql+asyncpg://postgres:chimera@localhost:55433/chimera'
.venv\Scripts\python.exe -m alembic upgrade head
```

### 2. Environment

The harness reads Contexta's real configuration and **refuses to run** on the
`deterministic` embedding profile, because a SHA-256 hash has no semantic
content and would make every score meaningless.

```powershell
$env:CONTEXTA_EMBEDDING_PROVIDER='local'
$env:CONTEXTA_EMBEDDING_PROFILE='offline-qwen3-1024'
$env:CONTEXTA_EMBEDDING_DIMENSIONS='1024'
$env:CONTEXTA_LOCAL_MODEL_SERVER_URL='http://localhost:8001'
```

> `CONTEXTA_EMBEDDING_MODEL` must match whatever the model server is actually
> serving. It must be a 1024-dim model. If the server rejects the model name
> with *"does not match the active model"*, read the active name from the
> server and set `CONTEXTA_EMBEDDING_MODEL` (and a matching
> `CONTEXTA_EMBEDDING_VERSION`) to it.

### 3. Ollama (fully offline)

`gemma3:1b` is used for **both** the answering step and Contexta's own
extraction, so a run needs no external API key at all:

```powershell
ollama pull gemma3:1b

$env:CONTEXTA_LLM_BASE_URL='http://localhost:11434/v1'
$env:CONTEXTA_LLM_MODEL='gemma3:1b'
$env:CONTEXTA_LLM_API_KEY='ollama'   # Ollama ignores it; the client requires it
```

Note that extraction quality is then bounded by a 1B model. That is a fair
trade for a fast offline loop, but it is *not* the same measurement as a run
with a production-grade extraction model — extraction and retrieval quality are
entangled. Use the same extractor for every run you intend to compare.

---

## Running

```powershell
# smoke test: 4 sessions, 2 questions
.venv\Scripts\python.exe benchmarks\CHIMERA\run_benchmark.py `
  --db-url "postgresql+asyncpg://postgres:chimera@localhost:55433/chimera" `
  --max-sessions 4 --limit 2 --tag smoke

# a full category only
.venv\Scripts\python.exe benchmarks\CHIMERA\run_benchmark.py `
  --categories temporal_contradiction,silent_revert_detection --tag temporal

# measure the rerank delta (both numbers are worth having)
.venv\Scripts\python.exe benchmarks\CHIMERA\run_benchmark.py --rerank off --tag no_rrf
.venv\Scripts\python.exe benchmarks\CHIMERA\run_benchmark.py --rerank on  --tag with_rrf

# ingestion only, then answer later against the same DB
.venv\Scripts\python.exe benchmarks\CHIMERA\run_benchmark.py --ingest-only --tag ingest
.venv\Scripts\python.exe benchmarks\CHIMERA\run_benchmark.py --skip-ingest --tag pass2
```

Useful flags: `--limit N`, `--max-sessions N`, `--categories a,b`,
`--ingest-concurrency N`, `--question-concurrency N`, `--tag NAME`.

### Regenerating the dataset

```powershell
.venv\Scripts\python.exe benchmarks\CHIMERA\generator.py --n-questions 500 --seed 7
```

> This **overwrites** `data/questions.jsonl`. Keep a copy of any hand edits.

---

## Editing the questions

`data/questions.jsonl` is the contract between you and the harness. One JSON
object per line:

```json
{
  "id": "q_e266470e",
  "number": 1,
  "category": "temporal_contradiction",
  "category_number": 1,
  "difficulty_tier": "multi_hop_decoy",
  "domains": ["conversation"],
  "question": "Which city does Priya_1 currently live in?",
  "gold_answer": "Bengaluru",
  "required_fact_ids": ["fact_1cac8e93", "fact_f979ffef"],
  "distractor_fact_ids": ["fact_11725de6"],
  "scoring_rubric": "Full credit for the corrected city only.",
  "expect_any_of": ["Bengaluru"],
  "forbidden": ["Pune"],
  "scoring": "match"
}
```

| Key | Effect |
|---|---|
| `question` | what the agent is asked |
| `gold_answer` | the reference answer |
| `expect_any_of` | **all** of these must appear in the answer (use for multi-part answers) |
| `forbidden` | if **any** of these appear, the answer fails — even if it also matches. Use for superseded secrets and injected commands |
| `scoring` | `match` (default), or `negative_recall` (passes only on honest abstention) |
| `required_fact_ids` / `distractor_fact_ids` | ground-truth linkage, shown in the report |
| `scoring_rubric` | shown in the report for human review |

You can rewrite gold answers, delete questions, or add your own — the harness
runs whatever is in the file. Re-running the generator overwrites it.

---

## Scoring

`PASS` when the answer matches the reference. Match order:

1. a forbidden token appears → **fail** (`leaked`)
2. `negative_recall` → pass only on honest abstention
3. empty answer → fail
4. abstained although the fact exists → fail (`abstained`)
5. every `expect_any_of` present → pass
6. gold answer present in the answer (normalised) → pass
7. numeric match → pass
8. gold token overlap ≥ 60% → pass
9. otherwise fail (`hallucinated` if the answer was confident)

Flags are recorded alongside the verdict and surfaced in the report as counts.
They exist for triage: `hallucinated` is the failure mode that matters most for a
memory product, because silent hallucination is worse than a visible gap.

---

## The HTML report

```powershell
.venv\Scripts\python.exe benchmarks\CHIMERA\report.py --latest
```

Single self-contained file, no server needed. Contains:

- headline accuracy, retrieval p50/p95/p99, answer latency, memories stored
- per-category accuracy and retrieval latency
- ingestion panel: per-session extraction log and every memory row persisted
- **searchable per-question audit log** — per question it shows the question,
  the reference answer, the ground-truth reference context, what Contexta
  retrieved and handed the agent (with score breakdown), what was saved in the
  DB while extracting, what the agent answered, the verdict, and the timing
  breakdown. Filter by text, category, or verdict.

---

## Categories

| # | Category | Stresses |
|---|---|---|
| 1 | temporal_contradiction | picking the currently-true fact among an update and a decoy |
| 2 | multi_hop_sessions | combining facts never co-located in the source |
| 3 | negative_recall | not hallucinating a plausible-but-absent fact |
| 4 | distractor_density | ranking under many near-identical decoys |
| 5 | update_vs_append | overwriting vs incorrectly duplicating |
| 6 | identity_resolution | alias drift with a colliding near-twin |
| 7 | decay_staleness | one early fact buried under volume |
| 8 | instruction_vs_fact | stored content that looks like a command |
| 9 | quantitative_aggregation | counting scattered events |
| 10 | precision_vs_recall | a list where one entry was reversed |
| 11 | code_call_chain | tracing a function through renames |
| 12 | silent_revert_detection | a fix quietly reintroduced |
| 13 | deprecated_secret_leakage | must not surface a rotated key |
| 14 | state_machine_simulation | ordered mutations to a final state |
| 15 | cross_domain_fusion | conversation + code + record |
| 16 | format_shift_identity | same entity as JSON, prose and table |
| 17 | unit_timezone_normalization | mixed units and timezones |
| 18 | adversarial_injection | stored text engineered to look like a system instruction |

---

## Known blocker

*(resolved — see below)*

`MemoryPipeline` / `FastMemoryOrchestrator.orchestrate` failed to persist any
observation that produced entity links:

```
sqlalchemy.exc.IntegrityError: ForeignKeyViolationError:
insert or update on table "memory_entity_link" violates foreign key constraint
"fk_memory_entity_link_memory_id_memory_record"
```

Cause: `contexta/models/entity.py:73` declares `MemoryEntityLink` with bare
`ForeignKey` columns and no `relationship()`. SQLAlchemy's unit of work derives
insert ordering from mapper relationships, not from bare foreign keys, so it has
no dependency edge and preserves construction order — the junction row is
emitted before its `memory_record` parent. The links are built by
`BulkEntityResolver.resolve_batch()` at line 270 of `contexta/core/pipeline.py`
but only added to the session at line 293.

Fixed in `contexta/core/pipeline.py` by flushing the memory and entity parents
before the junction rows are added (step 2c). Verified: session failures went
from 2/4 to 0/6 and memories persisted correctly.

The cleaner long-term fix is to declare real `relationship()` mappings on
`MemoryEntityLink` so the unit of work orders the inserts itself.

---

## Reading the results honestly

Accuracy is only meaningful when the corpus backing the questions has actually
been ingested. `--max-sessions N` truncates ingestion, so a small run answers
questions whose supporting facts were never stored. That produces a low score
that says more about ingestion coverage than about Contexta.

For a valid number, ingest the full corpus (`--max-sessions 0`, the default)
and run all 500 questions. The per-question log makes the difference obvious: if
the required fact is absent from `context_given_to_agent`, the failure is
ingestion coverage; if it is present but the answer is wrong, the failure is
retrieval or reasoning. That distinction is the main reason this harness keeps
the reference context next to the retrieved context.


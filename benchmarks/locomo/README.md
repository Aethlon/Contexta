# LoCoMo End-to-End Benchmark

This directory evaluates Contexta on the [LoCoMo](https://github.com/snap-research/locomo) (**Lo**ng **Co**nversational **Mo**ry) dataset: 10 synthetic multi-session conversations with 1,986 answerable and adversarial questions.

The current harness is end-to-end and answer-based, but it is benchmark-specific. It is not the public HTTP ingestion path, it does not run the durable observation/outbox boundary, and its score is not directly comparable with another system's self-reported result.

---

## 1. What the Current Run Measures

For each conversation, `run_benchmark.py`:

1. Converts every source session into messages and prepends the source session date as text.
2. Runs `ExtractionWorker` in the configured offline or online mode.
3. Applies source-date metadata and benchmark-local relative-date annotation for the supported expressions.
4. Runs memory deduplication, scoring, PostgreSQL persistence, entity resolution, inline embedding generation, and temporal/provenance projection.
5. Runs a dream-cycle knowledge-gap pass.
6. Embeds each question and calls the real `RetrievalEngine.retrieve()` with PostgreSQL-backed repositories.
7. Sends the retrieved memories and question to the configured answer generator.
8. Judges only the generated answer against the LoCoMo gold answer. For adversarial questions, the judge requires explicit abstention rather than accepting silence as correct.

The reported score is generated-answer correctness. It combines retrieval quality, extraction quality, answer-generation quality, and judge behavior.

This is not a retrieval-only benchmark. It does not report Recall@K or MRR for the gold evidence turns.

---

## 2. Current Components

| Stage | Current harness behavior |
| --- | --- |
| Database | PostgreSQL with pgvector; migrated with the current Alembic head |
| Extraction | `ExtractionWorker`; offline mode uses the local classifier/heuristic response path |
| Deduplication | `MemoryDeduplicator` |
| Scoring | `MemoryScoringEngine` |
| Persistence | `MemoryRepository.persist()` |
| Entities | `EntityResolver` |
| Embeddings | Local model server Qwen3 when healthy; BGE-small fastembed fallback |
| Retrieval | Current `RetrievalEngine` with dense, lexical, graph, weighted RRF, and optional local reranking |
| Answer generation | Ollama `gemma3:1b` by default |
| Judge | Ollama `gemma3:1b` by default; deterministic `strict_rule` is also available |
| Dream cycle | One synthetic-question and knowledge-gap pass per conversation |

Contexta does not generate final application answers itself. The Ollama step stands in for the calling application's LLM.

---

## 3. Prerequisites

A full run needs a migrated PostgreSQL database, the Contexta model server, and Ollama with the answer/judge model available.

```powershell
uv sync --extra dev
docker compose up -d postgres model-server
uv run alembic upgrade head
ollama pull gemma3:1b
```

Use an empty benchmark database for a clean run. The runner tries PostgreSQL URLs from `--db-url`, `BENCHMARK_DB_URL`, and the standard local ports 15432, 5432, and 55432.

The first model-server start can spend several minutes downloading local Qwen3 weights. The model server must be healthy on `http://localhost:8001` for the preferred embedding and reranking path.

---

## 4. Running the Benchmark

Full run:

```powershell
uv run python benchmarks/locomo/run_benchmark.py --generator-provider ollama --generator-model gemma3:1b --judge-mode ollama --judge-model gemma3:1b --retrieval-limit 20
```

A bounded smoke run can verify service wiring and write separate artifacts without replacing the baseline:

```powershell
uv run python benchmarks/locomo/run_benchmark.py --max-conversations 1 --max-questions 5 --generator-provider ollama --generator-model gemma3:1b --judge-mode ollama --judge-model gemma3:1b --retrieval-limit 20 --output-tag smoke_ollama
```

`--max-questions` limits each selected conversation and is not a representative full-dataset score. Use `--output-tag` for experiments; omitting it writes to the canonical `results.json` and `RESULTS.md` paths.

A full 10-conversation run performs thousands of model calls and can take hours. Do not run it as a quick unit test.

---

## 5. Output Artifacts

| File | Contents |
| --- | --- |
| `data/locomo10.json` | Vendored upstream LoCoMo subset |
| `results.json` | Raw aggregate metadata and per-question records |
| `RESULTS.md` | Formatted aggregate and run counters |
| `run_benchmark.py` | End-to-end ingestion, retrieval, generation, and judging harness |

The current raw artifact stores aggregate scores, pipeline counters, token counters, elapsed time, conversation count, retrieval diagnostics, generator/judge provenance, and per-question answers/verdicts. The runner also supports tagged output so experimental runs do not replace the checked-in baseline.

For complete reproducibility, future releases should additionally record the UTC run timestamp, Git revision and dirty-worktree state, full command line, dataset checksum, Alembic revision, extraction provider/model, actual embedding backend/vector width, reranker backend, inference settings, hardware/concurrency, and stage-level retry counts. These fields are not all present in the historical checked-in `results.json`.

---

## 6. Category Mapping

LoCoMo's `qa[].category` integer maps as follows:

| Category | Name | Count | Evaluation intent |
| --- | --- | ---: | --- |
| 1 | single-hop | 282 | Evidence is usually in one dialogue turn |
| 2 | temporal | 321 | Date or time-seeking answer |
| 3 | multi-hop | 96 | Evidence must be combined across turns or sessions |
| 4 | open-domain | 841 | General factual recall |
| 5 | adversarial | 446 | No supported answer; explicit abstention is required |

The category counts sum to the 1,986 questions in the recorded run.

---

## 7. Evaluation Rules

The judge prompt does not include retrieved memories. It sees only the question, gold answer or adversarial trap, and generated answer. This prevents a correct answer embedded in retrieved context from being counted without appearing in the generated response.

The optional `strict_rule` evaluator uses only the generated answer. It accepts exact/substring/numeric matches, token F1 of at least 0.40, or sufficient salient-token overlap. Adversarial questions require an explicit abstention phrase and reject the trap answer.

Neither mode is a human audit. Model judges can accept imprecise answers, as visible in rationales for broad semantic matches, and deterministic matching can encode dataset-specific phrasing assumptions.

---

## 8. Current LoCoMo Caveats

### Benchmark-Specific Ingestion

The harness calls core components directly, embeds inline, and uses `MemoryRepository.persist()`. It now persists source-relative `event_at`, `observed_at`, `temporal_precision`, and `temporal_basis` metadata, but it still does not call the public observation route, the durable ingestion ledger, the outbox relay, or Celery queues. Benchmark scores therefore validate the core path, not the complete deployment boundary.

### Temporal Validation Boundary

The harness supplies source session timestamps to the observation payload, normalizes supported relative expressions, and persists the resulting temporal fields. Relative expressions without a trustworthy source reference remain explicitly unresolved. The historical 65.4% temporal category remains a baseline for the legacy artifact; the tagged three-conversation run is a smoke result, not a controlled replacement.

### Retrieval Metadata Mismatch

The raw top-level field says `retrieval_limit: 15`. Per-question records report 20 retrieved memories, and the current CLI default is 20. Preserve this inconsistency as evidence of incomplete run metadata; do not silently choose one value as canonical without rerunning and recording the command.

### Token Accounting

Ollama prompt counts already include the answer prompt and retrieved context. The harness then adds its separately counted `context_tokens` to prompt and completion tokens when calculating `total_tokens` and average tokens per query. The reported 8,851,986 total and 4,457.2 average therefore double-count context.

The 82.2% figure against an assumed 25,000-token context is arithmetic, not a measured full-context baseline run, and it uses the double-counted average. It is not a validated token-savings result.

### Call Accounting

`UsageTracker.calls` records answer-generation calls in this run. It does not include every extraction, classifier, reranking, or judge call, so `1,986 LLM calls` must not be interpreted as total model activity.

### Model and Judge Provenance

The formatted report names `gemma3:1b`, but the raw artifact does not encode generator/judge mode or model IDs. Re-running with different settings can therefore produce a different score without an obvious metadata difference.

### Model and Vector Path

The preferred Qwen embedding is 1024-dimensional, while the current `memory_record` column is `vector(1536)`. The benchmark zero-pads both Qwen and BGE-small vectors to 1536. This does not validate a native 1024-dimensional production database path.

### Comparability

Do not compare this score directly with Mem0, Letta, or another system unless generator, judge, prompt, context construction, retrieval limit, ingestion path, and dataset filtering are controlled. The current harness does not run the assumed 25,000-token full-context comparator.

---

## 9. Quality-Gate Status

The focused engineering gate for temporal grounding, durable ingestion, and canonical retrieval is:

```powershell
uv run pytest tests/test_temporal_normalization.py tests/test_ingestion_outbox.py tests/test_retrieval_fusion.py tests/test_retrieval_engine.py -q
```

The current working tree passed 44/44 tests on September 24, 2026. This gate validates mechanics, not LoCoMo accuracy.

The LoCoMo runner has no minimum overall score, category floor, regression delta, or CI threshold. The current **78.6% overall correctness** in `RESULTS.md` is a recorded baseline, not a pass/fail gate.

See [`docs/Featuers/quality-gates.md`](../../docs/Featuers/quality-gates.md) for the full evidence policy.

---

## 10. Dataset Provenance

`data/locomo10.json` is vendored from [`snap-research/locomo`](https://github.com/snap-research/locomo). The paper is Maharana et al. (2024), *Evaluating Very Long-Term Conversational Memory of LLM Agents*. The conversations are synthetic and the QA pairs are annotated.

The current end-to-end harness does not use dialogue evidence IDs, so malformed evidence references from the earlier retrieval-only methodology do not affect the recorded answer-accuracy score.

## 11. Three-Conversation Validation

The tagged artifacts `results-three_conversations_5q_rrf_temporal.json` and `RESULTS-three_conversations_5q_rrf_temporal.md` contain a 3-conversation, 5-question-per-conversation smoke run. The run scored `7/15` (`46.7%`) with `generator_provider=model_server`; that provider returns the top retrieved memory as a proxy and is not an LLM answerer, so the score is not comparable to the prior Gemma/Ollama result.

A separate post-fix retrieval audit is stored in `results-three_conversations_retrieval_audit.json`. It evaluates the same 15 questions by checking whether the gold answer is present in the retrieved context. The current dense + lexical + graph RRF path retrieved usable evidence for `12/15` (`80.0%`). The remaining misses are concentrated in multi-hop/entity-combination questions and one answer whose gold wording is not present in the extracted source memory.

The continuation artifact `results-remaining_9x5_new_algo.json` covers conversations 2–10 with five questions each: 45 questions, 60.0% Ollama answer accuracy, and 66.7% gold-answer-containing retrieval context. The run used `gemma3:1b` for generation and judging with the FastEmbed fallback; it is a diagnostic continuation, not a representative full-dataset score. The raw records show that several failures are answer-selection or judge issues even when the gold evidence is present in the retrieved context.

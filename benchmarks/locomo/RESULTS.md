# LoCoMo End-to-End Benchmark Results

Recorded baseline from the current in-process end-to-end harness: real PostgreSQL + pgvector persistence, Contexta extraction/deduplication/scoring/entity components, `RetrievalEngine.retrieve()`, `gemma3:1b` answer generation, and answer-only evaluation without retrieved-context leakage.

This is a model-dependent baseline, not an enforced release threshold and not a controlled comparison with another memory system. See [`README.md`](README.md) for methodology and limitations.

## Run Summary

- Conversations evaluated: 10
- Questions scored: 1986
- Sessions ingested: 272
- Memories extracted: 5858
- Memories stored (post-dedup): 5848
- Memories deduped (discarded/merged): 10
- Entities created: 2678
- Dream cycles executed: 10
- Knowledge gaps identified: 2
- Extraction failures: 0
- Answer-generation calls recorded by the token tracker: 1986
- Generator failures recorded by the token tracker: 0
- Generator prompt tokens reported: 4593902
- Generator completion tokens reported: 42788
- Retrieved context tokens counted separately: 4215296
- Harness additive total: 8851986
- Harness average per query: 4457.2 tokens
- Arithmetic reduction versus an assumed 25000-token context: 82.2%
- Wall time: 20263.5s

The additive token total is not a unique-token count: generator prompt tokens already include the supplied context, which the harness adds again through `context_tokens`. The 82.2% figure is therefore not a validated token-savings result. No full-context baseline run is included in the artifact.

## Overall

| category | n | accuracy |
|---|---:|---:|
| overall | 1986 | 0.786 |

## By Category

| category | n | accuracy |
|---|---:|---:|
| single-hop | 282 | 0.684 |
| temporal | 321 | 0.654 |
| multi-hop | 96 | 0.698 |
| open-domain | 841 | 0.805 |
| adversarial | 446 | 0.928 |

## Quality-Gate Interpretation

- The runner defines no minimum accuracy, category floor, or regression threshold.
- The current overall score is a baseline for future controlled reruns, not a pass/fail gate.
- The focused temporal, durable-ingestion, and retrieval regression gate passed 44/44 tests on September 24, 2026; those tests validate mechanics, not this score.
- The benchmark-specific ingestion path does not exercise the public durable observation ledger or outbox relay.
- This historical baseline predates the temporal/provenance persistence fields; the tagged validation run and retrieval audit cover those fields separately.
- Raw metadata has a retrieval-limit mismatch: top-level `retrieval_limit` is 15, while per-question records report 20 retrieved memories.
- The tagged three-conversation smoke run scored 7/15 with a top-memory proxy; the separate post-fix retrieval audit found gold evidence in 12/15 contexts. Neither replaces this baseline.
- The raw JSON does not record the full command, revision, migration head, judge mode, model IDs, embedding backend, or hardware used for this run.

See [`README.md`](README.md#8-current-locomo-caveats) before quoting this result.

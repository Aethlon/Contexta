# LoCoMo End-to-End Benchmark Results

End-to-end benchmark: real ingestion (extraction, dedup, scoring, persistence, entity resolution) into a real Postgres+pgvector database, real RetrievalEngine.retrieve(), generator=ollama/qwen3:4b, judge=ollama/qwen3:4b, and evaluation without context leakage. See `benchmarks/locomo/README.md` for full methodology.

- Conversations evaluated: 1
- Questions scored: 5
- Sessions ingested: 19
- Memories extracted: 419
- Memories stored (post-dedup): 419
- Memories deduped (discarded/merged): 0
- Entities created: 218
- Dream cycles executed: 1
- Knowledge gaps identified: 0
- Extraction failures: 0
- LLM calls: 5 (0 failed after retries)
- Token accounting: 8522 prompt + 2373 completion (10895 total); context subset=7838
- Average token consumption / query: 2179.0 tokens
- Efficiency vs 25k Full-Context baseline: 91.3% token reduction
- Wall time: 1187.2s

## Overall
| category | n | accuracy |
|---|---|---|
| overall | 5 | 0.400 |

## Retrieval proxy
- Answerable questions: 5
- Gold-answer-containing context: 4 (0.800)

## By category
| category | n | accuracy |
|---|---|---|
| single-hop | 2 | 0.000 |
| temporal | 2 | 1.000 |
| multi-hop | 1 | 0.000 |

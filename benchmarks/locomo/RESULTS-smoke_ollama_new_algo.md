# LoCoMo End-to-End Benchmark Results

End-to-end benchmark: real ingestion (extraction, dedup, scoring, persistence, entity resolution) into a real Postgres+pgvector database, real RetrievalEngine.retrieve(), generator=ollama/gemma3:1b, judge=ollama/gemma3:1b, and evaluation without context leakage. See `benchmarks/locomo/README.md` for full methodology.

- Conversations evaluated: 1
- Questions scored: 5
- Sessions ingested: 19
- Memories extracted: 419
- Memories stored (post-dedup): 419
- Memories deduped (discarded/merged): 0
- Entities created: 170
- Dream cycles executed: 1
- Knowledge gaps identified: 0
- Extraction failures: 0
- LLM calls: 5 (0 failed after retries)
- Token accounting: 12096 prompt + 93 completion (12189 total); context subset=11171
- Average token consumption / query: 2437.8 tokens
- Efficiency vs 25k Full-Context baseline: 90.2% token reduction
- Wall time: 364.2s

## Overall
| category | n | accuracy |
|---|---|---|
| overall | 5 | 0.800 |

## Retrieval proxy
- Answerable questions: 5
- Gold-answer-containing context: 4 (0.800)

## By category
| category | n | accuracy |
|---|---|---|
| single-hop | 2 | 1.000 |
| temporal | 2 | 0.500 |
| multi-hop | 1 | 1.000 |

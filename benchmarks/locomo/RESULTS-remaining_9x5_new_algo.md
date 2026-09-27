# LoCoMo End-to-End Benchmark Results

End-to-end benchmark: real ingestion (extraction, dedup, scoring, persistence, entity resolution) into a real Postgres+pgvector database, real RetrievalEngine.retrieve(), generator=ollama/gemma3:1b, judge=ollama/gemma3:1b, and evaluation without context leakage. See `benchmarks/locomo/README.md` for full methodology.

- Conversations evaluated: 9
- Questions scored: 45
- Sessions ingested: 253
- Memories extracted: 5463
- Memories stored (post-dedup): 5455
- Memories deduped (discarded/merged): 8
- Entities created: 1775
- Dream cycles executed: 9
- Knowledge gaps identified: 0
- Extraction failures: 0
- LLM calls: 45 (0 failed after retries)
- Token accounting: 102095 prompt + 821 completion (102916 total); context subset=93585
- Average token consumption / query: 2287.0 tokens
- Efficiency vs 25k Full-Context baseline: 90.9% token reduction
- Wall time: 4940.3s

## Overall
| category | n | accuracy |
|---|---|---|
| overall | 45 | 0.600 |

## Retrieval proxy
- Answerable questions: 45
- Gold-answer-containing context: 30 (0.667)

## By category
| category | n | accuracy |
|---|---|---|
| single-hop | 19 | 0.526 |
| temporal | 19 | 0.632 |
| multi-hop | 5 | 0.600 |
| open-domain | 2 | 1.000 |

# LoCoMo End-to-End Benchmark Results

End-to-end benchmark: real ingestion (extraction, dedup, scoring, persistence, entity resolution) into a real Postgres+pgvector database, real RetrievalEngine.retrieve(), LLM-generated answers, and LLM-judged accuracy -- the same methodology Mem0/Letta use to report LoCoMo scores. See `benchmarks/locomo/README.md` for full methodology and caveats.

- Conversations evaluated: 1
- Questions scored: 199
- Sessions ingested: 19
- Memories extracted: 419
- Memories stored (post-dedup): 419
- Memories deduped (discarded/merged): 0
- Entities created: 218
- Dream cycles executed: 1
- Knowledge gaps identified: 0
- Extraction failures: 0
- LLM calls: 199 (0 failed after retries)
- Tokens: 2109 prompt + 11687 completion + 214036 context (227832 total)
- Average token consumption / query: 1144.9 tokens
- Efficiency vs 25k Full-Context baseline: 95.4% token reduction
- Wall time: 1375.2s

## Overall
| category | n | accuracy |
|---|---|---|
| overall | 199 | 0.990 |

## By category
| category | n | accuracy |
|---|---|---|
| single-hop | 32 | 1.000 |
| temporal | 37 | 0.973 |
| multi-hop | 13 | 1.000 |
| open-domain | 70 | 1.000 |
| adversarial | 47 | 0.979 |

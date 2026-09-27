# LoCoMo End-to-End Benchmark Results

> This tagged smoke artifact predates the metadata-rich report format. It used `generator=model_server/model-server`, which returns the top retrieved memory as a proxy rather than generating an LLM answer, and it used the `fastembed` backend. Its answer score is diagnostic only and is not comparable to the Gemma/Ollama baseline. A post-fix retrieval audit is reported separately in `results-three_conversations_retrieval_audit.json` and `README.md`.

- Conversations evaluated: 3
- Questions scored: 15
- Sessions ingested: 70
- Memories extracted: 1451
- Memories stored (post-dedup): 1448
- Memories deduped (discarded/merged): 3
- Entities created: 661
- Dream cycles executed: 3
- Knowledge gaps identified: 0
- Extraction failures: 0
- LLM calls: 15 (0 failed after retries)
- Token counters from the historical runner: 33377 prompt + 1083 completion + 33218 context (67678 total)
- The historical total double-counts context; no token-savings claim is made from it.
- Average token consumption / query: 4511.9 tokens (not a controlled efficiency comparison)
- Wall time: 1353.8s

## Overall
| category | n | accuracy |
|---|---|---|
| overall | 15 | 0.467 |

## By category
| category | n | accuracy |
|---|---|---|
| single-hop | 5 | 0.600 |
| temporal | 7 | 0.571 |
| multi-hop | 1 | 0.000 |
| open-domain | 2 | 0.000 |

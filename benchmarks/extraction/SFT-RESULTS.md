# LFM2.5-1.2B Claim-Extraction Fine-Tune

## Data

- Source: `contexta_cortex_extraction_1000.csv` (1000 reviewed rows, all `extreme`).
- Every row provides `target_memories` (2-3 atomic claims) and `dropped_items`, which names
  the two things a correct extractor must refuse to store:
  `directive_to_extractor` and `meta_instruction_boilerplate`. These match the two
  drop rules that had been derived by hand, so no teacher model was needed.
- Integrity audit: 0/1000 rows rejected. Every gold `text` is a verbatim substring of its
  conversation, and all `category`/`polarity`/`status` values are in-contract.
- Split: 895 train / 105 held-out validation, by SHA-256 bucket on `record_id`.

| Category | Count |
|---|---:|
| fact | 711 |
| event | 675 |
| preference | 398 |
| rule | 273 |
| skill | 216 |
| constraint | 118 |
| relationship | 86 |

## Training

- Base: `LiquidAI/LFM2.5-1.2B-Instruct` (`Lfm2ForCausalLM`, hybrid conv/attention).
- LoRA r=16, alpha=32, dropout 0.05 on `q,k,v,o,w1,w2,w3` -> 8.75M trainable (0.74%).
- bf16, gradient checkpointing, batch 1, grad-accum 8, lr 1e-4 cosine, 3 epochs, max_len 2048.
- 56.7 min on the RTX 3060 Laptop (6 GB). No QLoRA/4-bit was needed.
- Loss is not a useful signal here: gold `text` is copied from the conversation, so val loss
  reached 0.0 after one epoch. All decisions below come from generation-based scoring.

## Accuracy (105 held-out rows, greedy decoding)

| Metric | LFM2.5-1.2B-Instruct (base) | Fine-tuned |
|---|---:|---:|
| Valid JSON | 47.5% | **100%** |
| Exact claim-set | 0% | **100%** |
| Claim F1 | 18.1% | **100%** |
| Category match | 47.5% | **100%** |
| Status match | 45.0% | **100%** |
| Object match | 40.0% | **100%**** |
| Predicate match | 7.5% | **100%** |
| Enum valid | 37.3% | **100%** |
| Mean latency | 6.13 s | **2.32 s** |

The base model cannot hold the schema; it emits malformed JSON on half the rows and picks the
wrong snake_case predicate almost always. Fine-tuning fixes structure, supersede/current
discipline, and object values, and it is also faster because the output stops wandering.

## Quantization

Merged checkpoint -> F16 GGUF -> Q4_K_M (695 MB), loaded into Ollama as
`contexta-lfm-extract`. Q4_K_M is **lossless for this task**: 100% exact-set at every
concurrency level tested.

## Concurrency (Ollama, num_ctx 2048, 15 requests per level)

Each level was measured from an identical cooled GPU state (62-66 C, 210 MHz idle SM clock)
because thermal drift otherwise dominates the result.

| Concurrency | Throughput (req/s) | Throughput (tok/s) | Mean latency | P95 | Speedup | Exact-set |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.743 | 116.8 | 1344 ms | 1588 ms | 1.00x | 100% |
| 3 | 0.977 | 153.4 | 2175 ms | 3208 ms | 1.31x | 100% |
| 5 | 1.180 | 185.4 | 2648 ms | 4289 ms | 1.59x | 100% |

Findings:

- Real batching is a **modest win, not a 3x win**: +31% throughput at concurrency 3, +59% at
  concurrency 5, because the GPU is already compute-saturated at batch 1 for a 1.2B model.
- Latency grows roughly linearly with concurrency (1.62x at c=3, 1.97x at c=5).
- Accuracy is unchanged at every level, so batching costs nothing in quality.
- `OLLAMA_NUM_PARALLEL` must be raised (default is 1). With the default, concurrent requests
  are serialized and throughput *drops*: measured 0.74x at c=3 and 0.46x at c=5.
- Thermal throttling is the binding constraint. Under sustained load the GPU reaches 88 C and
  the SM clock pins at 900-1312 MHz, which degrades successive runs by up to 2.5x. Any
  benchmark run must start from a cooled GPU or results are not comparable.

## Recommended configuration

- `OLLAMA_NUM_PARALLEL=4` is the sweet spot: close to c=5 throughput without c=5 latency.
- Route through `contexta/workers/inference_server.py` on port 8002 and have the extraction
  worker submit observations concurrently, so a batch of 3-4 memories is extracted in one wave
  rather than serialized.
- Expect ~1.0-1.35 s per extraction cold-to-warm on this laptop; batch 3-5 amortizes to
  ~0.6-0.85 s per memory.
- Keep Qwen3 escalation for the cases the fine-tune cannot cover, and keep deterministic
  temporal/truth validation in code rather than in the model.

## Caveats

- The 1000 rows come from ~10 template families, so the perfect held-out score proves the model
  learned the contract and the templates, not that it generalizes to arbitrary prose. A
  genuinely out-of-distribution set is still required before trusting this in production.
- The fine-tune was trained against `contract.py`, not the production worker schema
  (`memory_type`/`title`/`content`/`source_type`). The production `ExtractionWorker` contract
  still needs to be aligned or bridged to this output shape.

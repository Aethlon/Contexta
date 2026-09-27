# Contexta Extraction Pilot — First 50 Extreme Conversations

## Scope

- Dataset: `contexta_extreme_200_conversations.csv`
- Rows evaluated: first 50
- Dataset difficulty: 50/50 `extreme`
- Date: 2026-09-25
- Runtime: local Ollama on CPU

## Models

| Model | Purpose | Size |
|---|---|---:|
| `LiquidAI/LFM2.5-350M` Q4_K_M | Candidate fast extractor | 229 MB |
| `LiquidAI/LFM2.5-350M` Q8_0 | Higher-fidelity LFM check | 379 MB |
| `LiquidAI/LFM2.5-1.2B-Instruct` Q4_K_M | Larger LFM candidate | 730 MB |
| `Qwen3-4B-Instruct-2507` Q4_K_M | Quality control | 2.5 GB |
| `qwen3:4b` | Thinking-build diagnostic | 2.5 GB |
| `openbmb/minicpm5` | SOTA-class 1B non-thinking alternative | 688 MB |
| `granite4:1b-h` | Hybrid reasoning 1B alternative | 1.6 GB |

The default `qwen3:4b` model is a thinking build. It spent 133–175 seconds per row and mixed reasoning with the answer, so `Qwen3-4B-Instruct-2507` was used as the fair non-thinking control.

LFM2.5-2.6B was also downloaded and tested on the first three rows. It is a newer agentic/thinking build whose Ollama template always opens a reasoning block; it ignored `think: false`, consumed the output budget reasoning, and produced 0/3 strict-schema responses in 7.5–18.4 seconds. A full 50-row run was stopped because the failure was runtime-level rather than quality-level.

## Aggregate results

| Configuration | Valid JSON | Mean claims | Complete claim schema | Evidence grounded | Anchor coverage | Mean latency | P95 latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| LFM2.5-350M Q4, strict schema | 0% | 0.00 | 0% | 0% | 0% | 316 ms | 472 ms |
| LFM2.5-350M Q4, relaxed schema | 100% | 1.20 | 0% | 69.3% | 14.7% | 416 ms | 612 ms |
| LFM2.5-350M Q8, recoverable output | 86% | 0.86 | 0% | low | 14.1% | ~400 ms | ~600 ms |
| LFM2.5-1.2B-Instruct, recoverable statements | 96% | 2.92 | 0% | 48.5% | 82.1% | 666 ms | 782 ms |
| Qwen3-4B-Instruct-2507 | 100% | 4.18 | 100% | 97.4% | 89.7% | 32.8 s | 56.9 s |
| MiniCPM5 (688 MB), strict schema | 100% | 1.20 | 100% | 53.7% | 86.8% | 2.8 s | 3.9 s |
| Granite 4.0 1B-H (1.6 GB), strict schema | 100% | 1.72 | 100% | 36.2% | 72.4% | 3.9 s | 11.6 s |

Both new candidates satisfied the strict claim schema on all 50 rows with no JSON repairs, which neither LFM build managed.

Anchor coverage is a directional scenario-term check, not a gold-standard precision/recall score.

## Representative failures

### LFM2.5-350M

For the address conversation, relaxed output was:

```json
{"claims": [{"claim": "short fact", "evidence": "London"}]}
```

It missed the move to Manchester, treated the temporary London visit as a residence claim, and produced no subject, predicate, polarity, status, or confidence.

Other outputs copied generic trailing instructions such as:

```json
{"claims": [{"claim": "One more correction", "evidence": "2026-10-30"}]}
```

### LFM2.5-1.2B-Instruct

LFM 1.2B produced useful memory statements, but used a different shape (`status` + `memories`) instead of the requested claim schema. After normalizing that shape, it recovered 2.92 statements per conversation and reached 82.1% scenario-anchor coverage.

It still made important errors, including selecting the first interpretation of a relative date and missing the primary scenario in a later correction-only conversation. It is a promising **fast candidate generator**, not yet a safe canonical extractor.

### Qwen3-4B-Instruct

Qwen produced complete, grounded JSON, but made semantic mistakes:

- Kept `My old address was London until 2026-08-19` as `current` instead of superseded.
- Represented the address object as `address`, not `London/Manchester`.
- Marked the temporary London visit as `current` instead of `temporary`.
- On one relative-date conversation, extracted only the generic correction and missed the actual scheduling scenario.
- Produced a malformed date in one evidence-bearing claim.

These failures show that structural JSON validity is not equivalent to correct memory extraction.

### MiniCPM5

MiniCPM5 was the only 1B model to reach 86.8% anchor coverage, matching LFM2.5-1.2B within one point, and it emitted the exact claim schema every time. Its weaknesses are coverage breadth (1.20 claims per conversation) and evidence grounding (53.7%), plus roughly 4x the latency of LFM 1.2B because it is a 688 MB dense model rather than a 730 MB hybrid.

### Granite 4.0 1B-H

Granite was the weakest of the 1B group on quality (72.4% anchor, 36.2% grounded) and the slowest. On 8 of 50 rows it drifted into verbose multi-claim output of 4-7 claims, pushing latency to 10-16 seconds and evidence grounding below 0.5 on those rows.

## Decision

LFM2.5-350M is not acceptable as the final zero-shot extraction model for this dataset. Its speed is excellent, but it loses the primary claims and cannot satisfy the structured claim contract.

LFM2.5-1.2B-Instruct is the best LFM candidate so far: it is roughly 50x faster than the Qwen control and preserves most scenario anchors. However, it does not reliably produce the required claim fields or resolve temporal corrections, so it must be followed by deterministic parsing and truth validation.

MiniCPM5 is the best schema-compliant fast candidate. It is 3-4x faster than Qwen3-4B, never required a JSON repair, and retained 86.8% of scenario anchors, so it is the strongest option when strict claim structure is required without fine-tuning. Granite 4.0 1B-H is rejected: it is slower and less accurate than both LFM 1.2B and MiniCPM5.

Qwen3-4B-Instruct is the strongest quality candidate, but it still requires:

- deterministic temporal normalization
- explicit current/superseded validation
- object-value validation
- evidence/claim consistency checks
- escalation for low-confidence or contradictory claims

## Recommended next experiment

1. Build reviewed gold labels for at least one complete template family and a matching number of ordinary conversations.
2. Use LFM2.5-1.2B-Instruct as the fast candidate generator and add deterministic claim normalization.
3. Use Qwen3-4B-Instruct as the escalation/verification model for low-confidence temporal or contradiction cases.
4. If needed, create silver labels from Qwen plus deterministic validation, manually review them, and LoRA-finetune LFM2.5-1.2B.
5. Keep LFM2.5-350M only as a fast triage/compression candidate unless fine-tuned.

## Artifacts

- `results-50/summary-50.json`
- `results-50/qwen3_4b-instruct-2507-q4_K_M.jsonl`
- `results-50/hf.co_LiquidAI_LFM2.5-350M-GGUF_Q4_K_M.jsonl`
- `results-50/lfm-relaxed.jsonl`
- `results-50/lfm-relaxed-summary.json`
- `results-50/qwen3-thinking-diagnostic.jsonl`
- `results-50-q8/summary-50.json`
- `results-50-lfm12/summary-50.json`
- `results-50-lfm12/hf.co_LiquidAI_LFM2.5-1.2B-Instruct-GGUF_Q4_K_M.jsonl`
- `results-50-minicpm-granite/summary-50.json`
- `results-50-minicpm-granite/openbmb_minicpm5_latest.jsonl`
- `results-50-minicpm-granite/granite4_1b-h.jsonl`

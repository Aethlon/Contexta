"""Generate on the held-out split and score against the gold memories.

Loss is not informative here: the gold `text` fields are verbatim conversation
spans, so a fine-tuned model reaches near-zero loss by copying. This script
measures what actually matters - emitted JSON, claim-set accuracy, and the
supersede/current discipline the corpus is designed to probe.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contract import evaluate, parse_memories

DEFAULT_OUTPUT = Path("benchmarks/extraction/sft/output")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def summarize(name: str, metrics: list[dict[str, Any]], seconds: float) -> dict[str, Any]:
    def mean(key: str) -> float:
        return round(statistics.mean(item[key] for item in metrics), 4)

    latencies = sorted(item["latency_ms"] for item in metrics)
    return {
        "model": name,
        "count": len(metrics),
        "json_valid_rate": mean("json_valid"),
        "exact_set_rate": mean("exact_set"),
        "claim_f1": mean("claim_f1"),
        "claim_precision": mean("claim_precision"),
        "claim_recall": mean("claim_recall"),
        "category_match": mean("category_match"),
        "status_match": mean("status_match"),
        "object_match": mean("object_match"),
        "predicate_match": mean("predicate_match"),
        "text_grounded_rate": mean("text_grounded_rate"),
        "enum_valid_rate": mean("enum_valid_rate"),
        "mean_claims": mean("predictions"),
        "mean_latency_ms": mean("latency_ms"),
        "p95_latency_ms": round(latencies[max(0, int(len(latencies) * 0.95) - 1)], 2),
        "wall_clock_minutes": round(seconds / 60, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score a model on the held-out split")
    parser.add_argument("--model", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("benchmarks/extraction/sft/data"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-new-tokens", type=int, default=400)
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(args.model, padding_side="left")
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16).to(device)
    model.eval()
    model.config.use_cache = True

    rows = load_jsonl(args.data_dir / "val.jsonl")
    if args.limit:
        rows = rows[: args.limit]

    metrics: list[dict[str, Any]] = []
    details_path = args.output_dir / f"eval-{args.name}-details.jsonl"
    details_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()

    with details_path.open("w", encoding="utf-8") as handle, torch.inference_mode():
        for start in range(0, len(rows), args.batch_size):
            chunk = rows[start : start + args.batch_size]
            prompts = [
                tokenizer.apply_chat_template(row["messages"][:-1], tokenize=False, add_generation_prompt=True)
                for row in chunk
            ]
            encoded = tokenizer(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to(device)
            tick = time.time()
            outputs = model.generate(
                **encoded,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=tokenizer.pad_token_id,
            )
            elapsed = (time.time() - tick) * 1000 / len(chunk)
            for row, output in zip(chunk, outputs):
                text = tokenizer.decode(output[encoded["input_ids"].shape[1] :], skip_special_tokens=True)
                memories, parse_error = parse_memories(text)
                metric = evaluate(
                    row["messages"][1]["content"],
                    memories,
                    row["memories"],
                    parse_error,
                    elapsed,
                )
                metrics.append(metric)
                handle.write(
                    json.dumps(
                        {
                            "record_id": row["record_id"],
                            "predictions": memories,
                            "references": row["memories"],
                            "metrics": metric,
                            "raw": text,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            done = start + len(chunk)
            print(
                f"{args.name} {done}/{len(rows)} "
                f"json={metrics[-1]['json_valid']} "
                f"exact={metrics[-1]['exact_set']} "
                f"f1={metrics[-1]['claim_f1']} "
                f"lat={elapsed:.0f}ms",
                flush=True,
            )

    summary = summarize(args.name, metrics, time.time() - started)
    (args.output_dir / f"eval-{args.name}-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

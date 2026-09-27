"""Measure single-request vs batched (concurrent) inference against Ollama.

The interesting question for a memory kernel is not per-request latency but
whether N concurrent extractions cost N times as much wall clock. This script
fires the same workload at several concurrency levels and reports latency,
throughput and accuracy together, so a batching win cannot hide an accuracy loss.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contract import evaluate, parse_memories

OLLAMA_URL = "http://localhost:11434/api/chat"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


async def one_request(
    client: httpx.AsyncClient,
    model: str,
    row: dict[str, Any],
    num_predict: int,
    num_ctx: int,
) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": row["messages"][:-1],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.0, "num_predict": num_predict, "num_ctx": num_ctx},
    }
    started = time.perf_counter()
    response = await client.post(OLLAMA_URL, json=body)
    elapsed = (time.perf_counter() - started) * 1000
    response.raise_for_status()
    payload = response.json()
    text = str(payload.get("message", {}).get("content", ""))
    memories, parse_error = parse_memories(text)
    return {
        "record_id": row["record_id"],
        "latency_ms": elapsed,
        "eval_tokens": int(payload.get("eval_count", 0) or 0),
        "metrics": evaluate(
            row["messages"][1]["content"],
            memories,
            row["memories"],
            parse_error,
            elapsed,
        ),
    }


async def run_level(
    model: str,
    rows: list[dict[str, Any]],
    concurrency: int,
    num_predict: int,
    num_ctx: int,
    warmup: int,
) -> dict[str, Any]:
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(timeout=600.0, limits=limits) as client:
        if warmup:
            await asyncio.gather(
                *(one_request(client, model, row, num_predict, num_ctx) for row in rows[:warmup])
            )
        started = time.perf_counter()
        results: list[dict[str, Any]] = []
        for start in range(0, len(rows), concurrency):
            batch = rows[start : start + concurrency]
            results.extend(
                await asyncio.gather(
                    *(one_request(client, model, row, num_predict, num_ctx) for row in batch)
                )
            )
        wall = time.perf_counter() - started

    latencies = sorted(item["latency_ms"] for item in results)
    metrics = [item["metrics"] for item in results]
    total_tokens = sum(item["eval_tokens"] for item in results)
    return {
        "concurrency": concurrency,
        "requests": len(results),
        "wall_clock_s": round(wall, 2),
        "throughput_req_per_s": round(len(results) / wall, 4),
        "throughput_claims_per_s": round(total_tokens / wall, 2),
        "mean_latency_ms": round(statistics.mean(latencies), 1),
        "p50_latency_ms": round(latencies[len(latencies) // 2], 1),
        "p95_latency_ms": round(latencies[max(0, int(len(latencies) * 0.95) - 1)], 1),
        "json_valid_rate": round(statistics.mean(item["json_valid"] for item in metrics), 4),
        "exact_set_rate": round(statistics.mean(item["exact_set"] for item in metrics), 4),
        "claim_f1": round(statistics.mean(item["claim_f1"] for item in metrics), 4),
        "category_match": round(statistics.mean(item["category_match"] for item in metrics), 4),
        "status_match": round(statistics.mean(item["status_match"] for item in metrics), 4),
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark concurrent extraction throughput")
    parser.add_argument("--model", default="contexta-lfm-extract")
    parser.add_argument("--data-dir", type=Path, default=Path("benchmarks/extraction/sft/data"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/extraction/sft/output/concurrency.json"))
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 2, 3, 5])
    parser.add_argument("--num-predict", type=int, default=400)
    parser.add_argument("--num-ctx", type=int, default=4096)
    parser.add_argument("--warmup", type=int, default=3)
    args = parser.parse_args()

    rows = load_jsonl(args.data_dir / "val.jsonl")[: args.limit]
    results = []
    for concurrency in args.concurrency:
        summary = await run_level(
            args.model, rows, concurrency, args.num_predict, args.num_ctx, args.warmup
        )
        results.append(summary)
        print(json.dumps(summary), flush=True)

    baseline = results[0]
    for item in results[1:]:
        item["speedup_vs_c1"] = round(
            (baseline["wall_clock_s"] / item["wall_clock_s"]) if item["wall_clock_s"] else 0.0, 3
        )
        item["latency_penalty_vs_c1"] = round(
            item["mean_latency_ms"] / baseline["mean_latency_ms"], 3
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"model": args.model, "results": results}, indent=2), encoding="utf-8")
    print(json.dumps({"model": args.model, "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

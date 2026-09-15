"""Scientific Benchmark Runner CLI for Contexta Memory Engine (50.5K Records).

Usage:
    .venv\\Scripts\\python.exe scripts/run_scientific_benchmark.py [--queries N] [--concurrency N] [--suite SUITE] [--no-ablation] [--profile-only]
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from contexta.mcp.service import ContextaMCPService
from contexta.benchmarks.evaluator import BenchmarkEvaluator


def print_banner(title: str):
    width = 75
    print("\n" + "=" * width, flush=True)
    print(f" {title}".center(width), flush=True)
    print("=" * width, flush=True)


async def main():
    parser = argparse.ArgumentParser(description="Contexta 50.5K Scientific Retrieval & Latency Benchmark")
    parser.add_argument("--queries", type=int, default=50, help="Number of test queries (default: 50)")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrency workers (default: 5)")
    parser.add_argument("--suite", type=str, default="all", help="Category suite: all, contexta_architecture, cloud_infra, multi_hop_graph")
    parser.add_argument("--no-ablation", action="store_true", help="Skip graph ablation test")
    parser.add_argument("--profile-only", action="store_true", help="Only run latency percentiles profiling")
    parser.add_argument("--user-id", type=str, default="contexta_benchmark_50k", help="Workspace user scope")
    parser.add_argument("--json-output", type=str, default="", help="Optional filepath to save JSON results")
    args = parser.parse_args()

    print_banner("CONTEXTA 50,500-RECORD SCIENTIFIC BENCHMARK SUITE")
    print(f"  Configuration:")
    print(f"    * Test queries:   {args.queries}")
    print(f"    * Concurrency:    {args.concurrency} parallel requests")
    print(f"    * Test Suite:     {args.suite}")
    print(f"    * Graph Ablation: {'Disabled' if args.no_ablation else 'Enabled (Hybrid vs Semantic-Only)'}")
    print(f"    * User Scope:     {args.user_id}")
    print("=" * 75)

    service = ContextaMCPService()
    evaluator = BenchmarkEvaluator(service)

    # 1. Inspect live system metrics
    print("\n[1/3] Probing Live Contexta System Health & Database State...")
    metrics = await service.get_metrics()
    db = metrics.get("database", {})
    reranker = metrics.get("reranker", {})
    print(f"  -> Total Memories:        {db.get('total_memories', 0):,}")
    print(f"  -> Total Entities:        {db.get('total_entities', 0):,}")
    print(f"  -> Total Graph Edges:     {db.get('total_edges', 0):,}")
    print(f"  -> Memory-Entity Links:   {db.get('total_memory_entity_links', 0):,}")
    print(f"  -> Local Neural Reranker: {reranker.get('status')} ({reranker.get('ping_ms', 0)}ms)")

    if args.profile_only:
        print_banner("LATENCY PROFILING UNDER CONCURRENCY")
        print(f"Firing {args.queries} requests with concurrency={args.concurrency}...")
        prof = await evaluator.profile_latency(
            num_requests=args.queries,
            concurrency=args.concurrency,
            mode="hybrid",
            user_id=args.user_id,
        )
        l = prof["latency_percentiles_ms"]
        print(f"\n  Throughput:   {prof['throughput_qps']} QPS  ({prof['completed_requests']}/{prof['total_requests']} completed)")
        print(f"  Error Rate:   {prof['error_rate_pct']}%")
        print(f"\n  Latency Percentiles (ms):")
        print(f"    * Min:      {l['min_ms']:>8.2f} ms")
        print(f"    * p50 (Med):{l['p50_ms']:>8.2f} ms")
        print(f"    * p75:      {l['p75_ms']:>8.2f} ms")
        print(f"    * p90:      {l['p90_ms']:>8.2f} ms")
        print(f"    * p95:      {l['p95_ms']:>8.2f} ms")
        print(f"    * p99:      {l['p99_ms']:>8.2f} ms")
        print(f"    * Max:      {l['max_ms']:>8.2f} ms")
        print(f"    * Mean:     {l['mean_ms']:>8.2f} ms (stddev: {l['stddev_ms']:.2f})")
        await service.close()
        return

    # 2. Run scientific benchmark suite
    print(f"\n[2/3] Executing {args.queries} Ground-Truth Retrieval Evaluations...")

    last_pct = 0
    def on_progress(done, total, metric):
        nonlocal last_pct
        pct = int((done / total) * 100)
        if pct >= last_pct + 10 or done == total:
            last_pct = pct
            print(f"  -> Progress: {done}/{total} ({pct}%) | Last Latency: {metric.latency_ms:.1f}ms | Rank: #{metric.rank}")

    report = await evaluator.run_suite(
        num_queries=args.queries,
        concurrency=args.concurrency,
        test_suite=args.suite,
        ablation=not args.no_ablation,
        user_id=args.user_id,
        progress_callback=on_progress,
    )

    # 3. Print Results Table
    print_banner("BENCHMARK RESULTS & RETRIEVAL QUALITY")
    print(f"  Throughput & Reliability:")
    print(f"    * Duration:         {report.duration_seconds:.2f}s")
    print(f"    * Throughput:       {report.throughput_qps:.2f} QPS")
    print(f"    * Total Evaluated:  {report.total_queries}")
    print(f"    * Successful:       {report.successful_queries}")
    print(f"    * Failed / Errors:  {report.failed_queries} ({report.error_rate_pct:.1f}%)")

    print(f"\n  Retrieval Quality Metrics (across 50.5K records):")
    print(f"    * Recall@1:         {report.recall_at_1:>6.2f}%")
    print(f"    * Recall@5:         {report.recall_at_5:>6.2f}%")
    print(f"    * Recall@10:        {report.recall_at_10:>6.2f}%")
    print(f"    * MRR:              {report.mrr:>6.4f}")
    print(f"    * nDCG@10:          {report.ndcg_at_10:>6.4f}")

    lat = report.latency
    print(f"\n  Latency Distribution (End-to-End Hybrid 3-Layer):")
    print(f"    * Min Latency:      {lat.min_ms:>8.2f} ms")
    print(f"    * p50 (Median):     {lat.p50_ms:>8.2f} ms")
    print(f"    * p75:              {lat.p75_ms:>8.2f} ms")
    print(f"    * p90:              {lat.p90_ms:>8.2f} ms")
    print(f"    * p95:              {lat.p95_ms:>8.2f} ms")
    print(f"    * p99:              {lat.p99_ms:>8.2f} ms")
    print(f"    * Max Latency:      {lat.max_ms:>8.2f} ms")
    print(f"    * Mean +/- Std:     {lat.mean_ms:>8.2f} ms +/- {lat.stddev_ms:.2f} ms")

    if report.ablation:
        ab = report.ablation
        print_banner("GRAPH ABLATION ANALYSIS (HYBRID 3-LAYER vs SEMANTIC-ONLY)")
        print(f"  * Hybrid MRR:             {ab.get('hybrid_mrr')}")
        print(f"  * Semantic-Only MRR:      {ab.get('semantic_only_mrr')}")
        print(f"  * Hybrid Recall@1:        {ab.get('hybrid_recall_1_pct')}%")
        print(f"  * Semantic-Only Recall@1: {ab.get('semantic_only_recall_1_pct')}%")
        print(f"  * Graph MRR Lift:         +{ab.get('graph_mrr_lift_pct')}%")
        print(f"  * Graph Verification:     {'CONFIRMED POSITIVE LIFT' if ab.get('graph_contribution_verified') else 'NEUTRAL'}")

    if report.sample_evaluations:
        print_banner("SAMPLE GROUND-TRUTH QUERY EVALUATIONS")
        for i, s in enumerate(report.sample_evaluations[:6], 1):
            rank_str = f"#{s['target_rank']}" if s['target_rank'] > 0 else "Miss"
            print(f"  [{i}] Rank: {rank_str:<5} | Latency: {s['latency_ms']:>6.1f}ms | Score: {s['score']:.4f} (sem={s['semantic_score']:.3f}, graph={s['graph_score']:.3f})")
            print(f"      Q: {s['query'][:65]}...")
            print(f"      Matched: '{s['top_retrieved_title']}'")

    if args.json_output:
        out_path = Path(args.json_output)
        import dataclasses
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(dataclasses.asdict(report), f, indent=2)
        print(f"\n[Saved full JSON benchmark report to: {out_path.resolve()}]")

    await service.close()
    print_banner("BENCHMARK COMPLETE")


if __name__ == "__main__":
    asyncio.run(main())

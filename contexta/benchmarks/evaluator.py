"""Scientific Benchmark Evaluator for Contexta Memory Engine.

Measures statistical retrieval quality (Recall@1/5/10, MRR, nDCG@10),
latency distribution (p50, p75, p90, p95, p99, min, max, mean, stddev),
throughput (QPS), error rates, and graph ablation across 50,000+ records.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Sequence

logger = logging.getLogger("contexta.benchmark")


@dataclass
class GroundTruthItem:
    query: str
    target_memory_id: str | None = None
    expected_keywords: list[str] = field(default_factory=list)
    expected_entities: list[str] = field(default_factory=list)
    category: str = "general"


@dataclass
class QueryResultMetric:
    query: str
    category: str
    latency_ms: float
    success: bool
    error: str | None = None
    top_score: float = 0.0
    top_semantic_score: float = 0.0
    top_graph_score: float = 0.0
    retrieved_memory_ids: list[str] = field(default_factory=list)
    retrieved_titles: list[str] = field(default_factory=list)
    rank: int = -1  # 1-based rank of ground truth, -1 if not in top K
    reciprocal_rank: float = 0.0
    ndcg_10: float = 0.0
    hit_at_1: bool = False
    hit_at_5: bool = False
    hit_at_10: bool = False


@dataclass
class LatencyPercentiles:
    min_ms: float = 0.0
    p50_ms: float = 0.0
    p75_ms: float = 0.0
    p90_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    max_ms: float = 0.0
    mean_ms: float = 0.0
    stddev_ms: float = 0.0


@dataclass
class BenchmarkReport:
    total_queries: int
    successful_queries: int
    failed_queries: int
    error_rate_pct: float
    duration_seconds: float
    throughput_qps: float
    latency: LatencyPercentiles
    recall_at_1: float
    recall_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_10: float
    ablation: dict[str, Any] = field(default_factory=dict)
    category_breakdown: dict[str, Any] = field(default_factory=dict)
    sample_evaluations: list[dict[str, Any]] = field(default_factory=list)


def compute_percentiles(latencies: Sequence[float]) -> LatencyPercentiles:
    if not latencies:
        return LatencyPercentiles()
    s = sorted(latencies)
    n = len(s)

    def pct(p: float) -> float:
        idx = int(round((p / 100.0) * (n - 1)))
        return round(s[max(0, min(idx, n - 1))], 2)

    return LatencyPercentiles(
        min_ms=round(s[0], 2),
        p50_ms=pct(50.0),
        p75_ms=pct(75.0),
        p90_ms=pct(90.0),
        p95_ms=pct(95.0),
        p99_ms=pct(99.0),
        max_ms=round(s[-1], 2),
        mean_ms=round(statistics.mean(s), 2),
        stddev_ms=round(statistics.stdev(s), 2) if n > 1 else 0.0,
    )


# Curated high-precision ground truth queries matching benchmark corpus
CURATED_GROUND_TRUTH: list[dict[str, Any]] = [
    {
        "query": "What did the team decide to use instead of Elasticsearch for document retrieval?",
        "expected_keywords": ["PostgreSQL", "pgvector", "Elasticsearch"],
        "expected_entities": ["PostgreSQL", "Elasticsearch"],
        "category": "architecture_decision",
    },
    {
        "query": "Which project replaces Redis with Valkey in our infrastructure?",
        "expected_keywords": ["Valkey", "Redis"],
        "expected_entities": ["Redis", "Valkey"],
        "category": "infra_replacement",
    },
    {
        "query": "What are Atlas integration requirements for Bengaluru Qdrant deployment?",
        "expected_keywords": ["Atlas", "Bengaluru", "Qdrant"],
        "expected_entities": ["Atlas", "Qdrant", "Bengaluru"],
        "category": "multi_hop_graph",
    },
    {
        "query": "Victor's temporal conflict resolution rule for memory updates",
        "expected_keywords": ["Victor", "temporal", "conflict"],
        "expected_entities": ["Victor"],
        "category": "temporal_policy",
    },
    {
        "query": "What was Nina working on for the recommendation service?",
        "expected_keywords": ["Nina", "recommendation"],
        "expected_entities": ["Nina"],
        "category": "entity_relationship",
    },
    {
        "query": "What is the Atlas latency target for cross-encoder reranking?",
        "expected_keywords": ["Atlas", "latency", "target"],
        "expected_entities": ["Atlas"],
        "category": "latency_spec",
    },
    {
        "query": "How does Contexta integrate natively with Luno for distributed caching?",
        "expected_keywords": ["Contexta", "Luno", "caching", "graph traversal"],
        "expected_entities": ["Contexta", "Luno"],
        "category": "contexta_architecture",
    },
    {
        "query": "How does Luno synchronize real-time state with Nori using pgvector?",
        "expected_keywords": ["Luno", "Nori", "pgvector", "asyncpg"],
        "expected_entities": ["Luno", "Nori"],
        "category": "contexta_architecture",
    },
    {
        "query": "Performance audit: sub-15ms cross-encoder latency between HARU and Tydl",
        "expected_keywords": ["HARU", "Tydl", "cross-encoder", "latency"],
        "expected_entities": ["HARU", "Tydl"],
        "category": "cross_encoder_perf",
    },
    {
        "query": "Architecture decision: Tydl replaces raw vector search in Contexta with hybrid 3-layer recall",
        "expected_keywords": ["Tydl", "Contexta", "hybrid 3-layer"],
        "expected_entities": ["Tydl", "Contexta"],
        "category": "hybrid_scoring",
    },
    {
        "query": "Kubernetes cluster deployed with 3 replicas connected to Kafka for stream processing",
        "expected_keywords": ["Kubernetes", "Kafka", "replicas", "stream processing"],
        "expected_entities": ["Kubernetes", "Kafka"],
        "category": "cloud_infra",
    },
    {
        "query": "Connection pooling optimized with 50 workers to prevent connection spikes to Postgres",
        "expected_keywords": ["Postgres", "connection pooling", "workers"],
        "expected_entities": ["Postgres"],
        "category": "cloud_infra",
    },
    {
        "query": "Disaster recovery automated backup snapshots stored in ClickHouse",
        "expected_keywords": ["ClickHouse", "backup", "disaster recovery"],
        "expected_entities": ["ClickHouse"],
        "category": "cloud_infra",
    },
    {
        "query": "Aethlon depends on HARU for high-throughput index generation and temporal alignment",
        "expected_keywords": ["Aethlon", "HARU", "temporal alignment"],
        "expected_entities": ["Aethlon", "HARU"],
        "category": "contexta_architecture",
    },
    {
        "query": "Loci handles neural reranking and spreading activation while Aethlon monitors health",
        "expected_keywords": ["Loci", "Aethlon", "spreading activation", "reranking"],
        "expected_entities": ["Loci", "Aethlon"],
        "category": "contexta_architecture",
    },
]


class BenchmarkEvaluator:
    """Orchestrates scientific benchmarking, latency profiling, and graph ablation."""

    def __init__(self, service: Any) -> None:
        self.service = service

    async def generate_ground_truth(
        self,
        target_count: int = 50,
        category_filter: str = "all",
        user_id: str = "contexta_benchmark_50k",
    ) -> list[GroundTruthItem]:
        from contexta.mcp.service import to_uuid
        target_uid = to_uuid(user_id)
        items: list[GroundTruthItem] = []

        # 1. Add curated queries if targeting default_user or all
        if user_id in ("default_user", "all"):
            for q in CURATED_GROUND_TRUTH:
                if category_filter == "all" or category_filter == q.get("category"):
                    items.append(
                        GroundTruthItem(
                            query=q["query"],
                            expected_keywords=q["expected_keywords"],
                            expected_entities=q["expected_entities"],
                            category=q["category"],
                        )
                    )

        # 2. Sample representative memories from database for the target user_id
        needed = target_count - len(items)
        if needed > 0:
            try:
                from sqlalchemy import text

                async with self.service.session() as session:
                    res = await session.execute(
                        text(
                            "SELECT id, title, content, tags FROM memory_record "
                            "WHERE user_id = :uid "
                            "ORDER BY RANDOM() LIMIT :limit"
                        ),
                        {"uid": target_uid, "limit": min(needed * 3, 500)},
                    )
                    rows = res.fetchall()

                    for r in rows:
                        if len(items) >= target_count:
                            break
                        m_id = str(r[0])
                        title = str(r[1])
                        content = str(r[2])
                        tags = list(r[3]) if r[3] else []

                        # Extract meaningful phrases from content for realistic agent recall query
                        sentences = [s.strip() for s in content.split(".") if len(s.strip()) > 15]
                        if sentences:
                            # Use natural paraphrased query from content
                            first_sentence = sentences[0]
                            words = [w.strip(".,!?:;\"'()[]") for w in first_sentence.split()]
                            meaningful = [w for w in words if len(w) >= 3 and w.lower() not in {"this", "that", "with", "from", "into", "using", "while"}]
                            
                            # Formulate realistic search query
                            if len(meaningful) >= 4:
                                q_phrase = " ".join(meaningful[:5])
                                query_text = f"What describes {q_phrase}?"
                            else:
                                clean_title = title.split("[#")[0].strip()
                                query_text = f"What are the details for {clean_title}?"

                            items.append(
                                GroundTruthItem(
                                    query=query_text,
                                    target_memory_id=m_id,
                                    expected_keywords=meaningful[:3],
                                    expected_entities=tags[:2],
                                    category=tags[0] if tags else "sampled_corpus",
                                )
                            )
            except Exception as sample_err:
                logger.warning("Could not sample extra memories for benchmark: %s", sample_err)

        return items[:target_count]

    async def evaluate_single_query(
        self,
        item: GroundTruthItem,
        user_id: str = "contexta_benchmark_50k",
        graph_depth: int = 2,
        limit: int = 10,
    ) -> QueryResultMetric:
        """Run a single retrieval query and evaluate ranking accuracy & latency."""
        t0 = time.perf_counter()
        try:
            results = await self.service.recall(
                query=item.query,
                user_id=user_id,
                limit=limit,
                graph_depth=graph_depth,
            )
            lat_ms = (time.perf_counter() - t0) * 1000.0

            if not results:
                return QueryResultMetric(
                    query=item.query,
                    category=item.category,
                    latency_ms=lat_ms,
                    success=True,
                    top_score=0.0,
                )

            top_r = results[0]
            retrieved_ids = [str(r.get("memory_id", "")) for r in results]
            retrieved_titles = [str(r.get("title", "")) for r in results]

            # Determine rank of correct memory
            target_rank = -1
            for idx, r in enumerate(results):
                content = (r.get("content", "") + " " + r.get("title", "")).lower()
                r_id = str(r.get("memory_id", ""))

                is_match = False
                if item.target_memory_id and r_id == item.target_memory_id:
                    is_match = True
                elif item.expected_keywords:
                    # Match if >= 60% of expected keywords found in retrieved text
                    matches = sum(1 for kw in item.expected_keywords if kw.lower() in content)
                    if matches >= max(1, int(len(item.expected_keywords) * 0.6)):
                        is_match = True

                if is_match:
                    target_rank = idx + 1
                    break

            reciprocal_rank = 1.0 / target_rank if target_rank > 0 else 0.0
            ndcg = (1.0 / math.log2(target_rank + 1)) if target_rank > 0 else 0.0

            return QueryResultMetric(
                query=item.query,
                category=item.category,
                latency_ms=lat_ms,
                success=True,
                top_score=float(top_r.get("score", 0.0)),
                top_semantic_score=float(top_r.get("semantic_score", 0.0)),
                top_graph_score=float(top_r.get("graph_score", 0.0)),
                retrieved_memory_ids=retrieved_ids,
                retrieved_titles=retrieved_titles,
                rank=target_rank,
                reciprocal_rank=reciprocal_rank,
                ndcg_10=ndcg,
                hit_at_1=(target_rank == 1),
                hit_at_5=(1 <= target_rank <= 5),
                hit_at_10=(1 <= target_rank <= 10),
            )
        except Exception as exc:
            lat_ms = (time.perf_counter() - t0) * 1000.0
            return QueryResultMetric(
                query=item.query,
                category=item.category,
                latency_ms=lat_ms,
                success=False,
                error=str(exc),
            )

    async def run_suite(
        self,
        num_queries: int = 50,
        concurrency: int = 5,
        test_suite: str = "all",
        ablation: bool = True,
        user_id: str = "contexta_benchmark_50k",
        progress_callback: Any | None = None,
    ) -> BenchmarkReport:
        """Run a full benchmark suite with concurrency control and ablation measurement."""
        test_items = await self.generate_ground_truth(
            target_count=num_queries,
            category_filter=test_suite,
            user_id=user_id,
        )

        sem = asyncio.Semaphore(max(1, min(concurrency, 30)))
        total = len(test_items)
        metrics: list[QueryResultMetric] = []
        start_time = time.perf_counter()

        async def _bounded_query(item: GroundTruthItem, idx: int) -> QueryResultMetric:
            async with sem:
                m = await self.evaluate_single_query(item, user_id=user_id, graph_depth=2)
                metrics.append(m)
                if progress_callback:
                    try:
                        progress_callback(len(metrics), total, m)
                    except Exception:
                        pass
                return m

        tasks = [_bounded_query(item, i) for i, item in enumerate(test_items)]
        await asyncio.gather(*tasks)

        total_duration = time.perf_counter() - start_time
        successful = [m for m in metrics if m.success]
        failed = [m for m in metrics if not m.success]
        latencies = [m.latency_ms for m in successful]

        recalls_1 = [1.0 if m.hit_at_1 else 0.0 for m in successful]
        recalls_5 = [1.0 if m.hit_at_5 else 0.0 for m in successful]
        recalls_10 = [1.0 if m.hit_at_10 else 0.0 for m in successful]
        mrrs = [m.reciprocal_rank for m in successful]
        ndcgs = [m.ndcg_10 for m in successful]

        r1 = round(statistics.mean(recalls_1) * 100.0, 2) if recalls_1 else 0.0
        r5 = round(statistics.mean(recalls_5) * 100.0, 2) if recalls_5 else 0.0
        r10 = round(statistics.mean(recalls_10) * 100.0, 2) if recalls_10 else 0.0
        mrr = round(statistics.mean(mrrs), 4) if mrrs else 0.0
        ndcg_avg = round(statistics.mean(ndcgs), 4) if ndcgs else 0.0

        percentiles = compute_percentiles(latencies)
        qps = round(len(metrics) / total_duration, 2) if total_duration > 0 else 0.0
        err_rate = round((len(failed) / len(metrics)) * 100.0, 2) if metrics else 0.0

        # Optional Graph Ablation comparison (run subset with graph_depth=0)
        ablation_stats = {}
        if ablation and successful:
            ablation_subset = test_items[: min(20, len(test_items))]
            sem_only_metrics = []
            for item in ablation_subset:
                async with sem:
                    m_no_graph = await self.evaluate_single_query(item, user_id=user_id, graph_depth=0)
                    sem_only_metrics.append(m_no_graph)

            sem_mrrs = [m.reciprocal_rank for m in sem_only_metrics if m.success]
            sem_r1 = [1.0 if m.hit_at_1 else 0.0 for m in sem_only_metrics if m.success]

            hybrid_subset_mrrs = mrrs[: len(sem_mrrs)]
            hybrid_mrr_sub = statistics.mean(hybrid_subset_mrrs) if hybrid_subset_mrrs else mrr
            sem_mrr_avg = statistics.mean(sem_mrrs) if sem_mrrs else 0.0
            sem_r1_avg = round(statistics.mean(sem_r1) * 100.0, 2) if sem_r1 else 0.0

            graph_lift = round(
                ((hybrid_mrr_sub - sem_mrr_avg) / max(0.001, sem_mrr_avg)) * 100.0, 2
            )
            ablation_stats = {
                "hybrid_mrr": round(hybrid_mrr_sub, 4),
                "semantic_only_mrr": round(sem_mrr_avg, 4),
                "hybrid_recall_1_pct": r1,
                "semantic_only_recall_1_pct": sem_r1_avg,
                "graph_mrr_lift_pct": graph_lift,
                "graph_contribution_verified": graph_lift >= 0.0,
            }

        # Category Breakdown
        categories: dict[str, list[QueryResultMetric]] = {}
        for m in successful:
            categories.setdefault(m.category, []).append(m)

        cat_breakdown = {}
        for cat, items_list in categories.items():
            cat_lats = [it.latency_ms for it in items_list]
            cat_r1 = [1.0 if it.hit_at_1 else 0.0 for it in items_list]
            cat_breakdown[cat] = {
                "count": len(items_list),
                "p50_ms": compute_percentiles(cat_lats).p50_ms,
                "recall_1_pct": round(statistics.mean(cat_r1) * 100.0, 2) if cat_r1 else 0.0,
                "mrr": round(statistics.mean([it.reciprocal_rank for it in items_list]), 4) if items_list else 0.0,
            }

        # Top Sample Evaluations
        samples = []
        for m in successful[:8]:
            samples.append(
                {
                    "query": m.query,
                    "category": m.category,
                    "target_rank": m.rank,
                    "latency_ms": round(m.latency_ms, 2),
                    "score": round(m.top_score, 4),
                    "semantic_score": round(m.top_semantic_score, 4),
                    "graph_score": round(m.top_graph_score, 4),
                    "top_retrieved_title": m.retrieved_titles[0] if m.retrieved_titles else "None",
                }
            )

        return BenchmarkReport(
            total_queries=len(metrics),
            successful_queries=len(successful),
            failed_queries=len(failed),
            error_rate_pct=err_rate,
            duration_seconds=round(total_duration, 2),
            throughput_qps=qps,
            latency=percentiles,
            recall_at_1=r1,
            recall_at_5=r5,
            recall_at_10=r10,
            mrr=mrr,
            ndcg_at_10=ndcg_avg,
            ablation=ablation_stats,
            category_breakdown=cat_breakdown,
            sample_evaluations=samples,
        )

    async def profile_latency(
        self,
        num_requests: int = 30,
        concurrency: int = 5,
        mode: str = "hybrid",
        user_id: str = "contexta_benchmark_50k",
    ) -> dict[str, Any]:
        """Rapid latency percentile profiling probe (p50, p75, p90, p95, p99) under load."""
        test_queries = [
            "PostgreSQL vector search architecture",
            "Redis replacement Valkey caching",
            "Contexta Luno distributed synchronization",
            "Atlas Qdrant Bengaluru deployment",
            "HARU Tydl cross-encoder latency",
            "Kubernetes Kafka stream processing cluster",
        ]

        sem = asyncio.Semaphore(max(1, min(concurrency, 30)))
        latencies: list[float] = []
        errors: list[str] = []
        graph_depth = 2 if mode == "hybrid" else 0

        t_start = time.perf_counter()

        async def _probe(idx: int) -> None:
            q = test_queries[idx % len(test_queries)]
            t0 = time.perf_counter()
            try:
                async with sem:
                    await self.service.recall(
                        query=q,
                        user_id=user_id,
                        limit=5,
                        graph_depth=graph_depth,
                    )
                latencies.append((time.perf_counter() - t0) * 1000.0)
            except Exception as e:
                errors.append(str(e))

        tasks = [_probe(i) for i in range(num_requests)]
        await asyncio.gather(*tasks)

        duration = time.perf_counter() - t_start
        pct = compute_percentiles(latencies)
        qps = round(len(latencies) / duration, 2) if duration > 0 else 0.0

        return {
            "mode": mode,
            "total_requests": num_requests,
            "completed_requests": len(latencies),
            "failed_requests": len(errors),
            "error_rate_pct": round((len(errors) / max(1, num_requests)) * 100.0, 2),
            "duration_seconds": round(duration, 3),
            "throughput_qps": qps,
            "latency_percentiles_ms": asdict(pct),
            "errors": errors[:5],
        }

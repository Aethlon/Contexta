"""LongMemEval end-to-end benchmark for Contexta.

Evaluates Contexta's 3-Layer hybrid architecture (Postgres + pgvector + knowledge graph + neural reranker)
against the LongMemEval benchmark (ICLR 2025).

Tasks evaluated:
  - temporal-reasoning: Resolving time-based questions and temporal ordering across sessions.
  - single-session: Specific needle extraction from user, assistant, or preference statements.
  - multi-session: Synthesizing evidence distributed across multiple distinct chat sessions.
  - knowledge-update: Handling facts that change or supersede previous statements over time.
  - abstention: Detecting unmentioned facts and declining to answer (zero-hallucination test).

Usage:
    .venv\\Scripts\\python.exe benchmarks/longmemeval/run_benchmark.py [--max-instances N] [--concurrency N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from contexta.config.settings import get_settings  # noqa: E402
from contexta.core.context.builder import ContextBuilder  # noqa: E402
from contexta.core.pipeline import FastMemoryOrchestrator  # noqa: E402
from contexta.core.retrieval.engine import RetrievalEngine, RetrievalResult  # noqa: E402
from contexta.core.schemas import (  # noqa: E402
    ContextConfig,
    ContextRequest,
    ObservationPayload,
    RetrievalQuery,
)
from contexta.models.memory import MemoryRecord  # noqa: E402
from contexta.repositories.entity_repo import (  # noqa: E402
    EntityEdgeRepository,
    EntityRepository,
    MemoryEntityLinkRepository,
)
from contexta.repositories.memory_repo import MemoryRepository  # noqa: E402
from contexta.services.embedding import EmbeddingService  # noqa: E402

logging.basicConfig(level=logging.WARNING)

DATA_PATH = REPO_ROOT / "benchmarks" / "longmemeval" / "data" / "longmemeval_oracle.json"
RESULTS_JSON_PATH = REPO_ROOT / "benchmarks" / "longmemeval" / "results.json"
RESULTS_MD_PATH = REPO_ROOT / "benchmarks" / "longmemeval" / "RESULTS.md"

DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:55432/contexta"
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
DB_VECTOR_DIM = 1536
RETRIEVAL_LIMIT = 15


# ─── Embedding Provider ──────────────────────────────────────────────────


class FastEmbedProvider:
    """Local semantic embedding provider (fastembed/BGE-small), zero-padded to 1536 dims."""

    def __init__(self, model) -> None:
        self._model = model

    def _embed_sync(self, text: str) -> list[float]:
        vec = list(self._model.embed([text]))[0].tolist()
        if len(vec) < DB_VECTOR_DIM:
            vec = vec + [0.0] * (DB_VECTOR_DIM - len(vec))
        return vec

    def _embed_batch_sync(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        results = []
        for vec in self._model.embed(texts, batch_size=64):
            v = vec.tolist()
            if len(v) < DB_VECTOR_DIM:
                v = v + [0.0] * (DB_VECTOR_DIM - len(v))
            results.append(v)
        return results

    async def embed(self, text: str) -> list[float]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._embed_sync, text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._embed_batch_sync, texts)


def load_fastembed_model():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=EMBEDDING_MODEL_NAME)


async def call_ollama_answer(
    client: httpx.AsyncClient,
    *,
    question: str,
    memories: list[MemoryRecord],
    model: str,
    base_url: str,
    context_text: str | None = None,
    max_tokens: int = 256,
) -> str:
    if context_text is None:
        context_lines = []
        for memory in memories:
            timestamp = memory.event_at or memory.observed_at or memory.valid_from
            label = f"[{timestamp.strftime('%d %B %Y')}] " if timestamp is not None else ""
            context_lines.append(f"- {label}{memory.title}: {memory.content}")
        context = "\n".join(context_lines) or "(no relevant memories)"
    else:
        context = context_text
    system_prompt = (
        "Answer the question using only the supplied memories. "
        "Use exact dates when the question asks when. "
        "If the memories do not contain the answer, say not mentioned. "
        "For list questions, include every supported item. "
        "Do not invent details. Output only the final answer, without analysis or explanation."
    )
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Memories:\n{context}\n\nQuestion: {question}\nAnswer:"},
        ],
        "options": {
            "temperature": 0.1,
            "num_ctx": 4096,
            "num_predict": max(max_tokens, 768) if "qwen" in model.lower() else max_tokens,
        },
        "stream": False,
        "think": False,
    }
    response = await client.post(f"{base_url.rstrip('/')}/api/chat", json=body, timeout=120.0)
    if response.status_code == 404:
        fallback = await client.post(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            json={
                "model": model,
                "messages": body["messages"],
                "temperature": 0.1,
                "max_tokens": body["options"]["num_predict"],
            },
            timeout=120.0,
        )
        fallback.raise_for_status()
        content = fallback.json()["choices"][0]["message"]["content"]
    else:
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
        if not content and data.get("message", {}).get("thinking"):
            content = data["message"]["thinking"]
    content = re.sub(r"<think>.*?</think>", "", str(content), flags=re.DOTALL).strip()
    return content


# ─── Neural Reranker ─────────────────────────────────────────────────────


class LocalModelServerReranker:
    """Connects to Contexta local model server running BAAI/bge-reranker-base."""

    def __init__(self, server_url: str = "http://localhost:8001") -> None:
        self.server_url = server_url
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def rerank(
        self,
        query: RetrievalQuery,
        results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        if not results:
            return results
        client = self._get_client()
        docs = [r.memory.content for r in results]
        try:
            resp = await client.post(
                f"{self.server_url}/v1/rerank",
                json={"query": query.query_text, "documents": docs, "top_n": len(docs)},
            )
            if resp.status_code == 200:
                data = resp.json()
                score_map = {
                    item["index"]: float(item.get("relevance_score", item.get("score", 0.0)))
                    for item in data.get("results", [])
                }
                reranked = []
                for idx, r in enumerate(results):
                    model_score = score_map.get(idx, 0.0)
                    blended_score = 0.85 * model_score + 0.15 * r.score
                    reranked.append(
                        RetrievalResult(
                            memory=r.memory,
                            score=blended_score,
                            semantic_score=model_score,
                            graph_score=r.graph_score,
                            importance_score=r.importance_score,
                            recency_score=r.recency_score,
                            keyword_score=getattr(r, "keyword_score", 0.0),
                        )
                    )
                reranked.sort(key=lambda x: x.score, reverse=True)
                return reranked
        except Exception as exc:
            logging.warning("Neural reranking fallback: %s", exc)
        return results

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ─── Date Parsing ────────────────────────────────────────────────────────


def parse_date_str(date_str: str) -> datetime | None:
    if not date_str:
        return None
    cleaned = re.sub(r"\([A-Za-z]+\)", "", date_str).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    for fmt in ("%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=None)
        except ValueError:
            pass
    return None


# ─── Ingestion Pipeline ──────────────────────────────────────────────────


async def ingest_instance(
    instance: dict,
    *,
    session_factory,
    user_id: UUID,
    organization_id: UUID,
    embedding_service: EmbeddingService,
    orchestrator: FastMemoryOrchestrator,
) -> int:
    sessions = instance.get("haystack_sessions", [])
    dates = instance.get("haystack_dates", [])
    source_id = str(instance.get("question_id", "longmemeval"))
    stored_count = 0

    for session_index, session_turns in enumerate(sessions):
        date_str = dates[session_index] if session_index < len(dates) else ""
        session_dt = parse_date_str(date_str)
        messages = []
        for turn_index, turn in enumerate(session_turns):
            content = str(turn.get("content", "")).strip()
            if not content:
                continue
            messages.append(
                {
                    "role": turn.get("role", "user"),
                    "content": content,
                    "text": content,
                    "occurred_at": session_dt.isoformat() if session_dt else None,
                    "observed_at": session_dt.isoformat() if session_dt else None,
                    "message_id": f"{source_id}:{session_index}:{turn_index}",
                    "timezone": "UTC",
                }
            )
        if not messages:
            continue

        payload = ObservationPayload(
            user_id=user_id,
            organization_id=organization_id,
            session_id=uuid4(),
            messages=messages,
            occurred_at=session_dt,
            observed_at=session_dt,
            source_id=source_id,
            timezone="UTC",
        )
        async with session_factory() as db_session:
            result = await orchestrator.orchestrate(payload, db_session)
            await db_session.commit()
            stored_count += result.stored_count
            memory_repo = MemoryRepository(db_session, tenant_id=organization_id)
            for memory_id in result.embedding_memory_ids:
                record = await memory_repo.get_by_id(UUID(memory_id))
                if record is not None:
                    await embedding_service.generate_and_store(
                        record,
                        memory_repo,
                        enqueue_on_failure=False,
                    )
            await db_session.commit()

    return stored_count


# ─── Evaluation & Offline Judging ────────────────────────────────────────


def judge_longmemeval(
    question_type: str,
    gold_answer: str | None,
    generated_answer: str,
    retrieved_contents: list[str],
    is_abstention: bool,
) -> bool:
    gen_lower = generated_answer.lower().strip()

    if is_abstention or gold_answer is None or not str(gold_answer).strip():
        # Model correctly abstains or indicates information is absent
        negative_indicators = [
            "not mentioned", "not available", "no information", "cannot find",
            "doesn't mention", "does not mention", "unmentioned", "unknown",
            "no record", "not specified", "unclear", "haven't mentioned",
        ]
        return any(ind in gen_lower for ind in negative_indicators)

    gold_str = str(gold_answer).lower().strip()
    if not gold_str:
        return False

    # 1. Exact or substring match in generated response or top context
    if gold_str in gen_lower:
        return True

    # 2. Word boundary match
    if re.search(r"\b" + re.escape(gold_str) + r"\b", gen_lower):
        return True

    # 3. Numeric & date normalized match
    gold_numbers = re.findall(r"\d+", gold_str)
    if gold_numbers and all(n in gen_lower for n in gold_numbers):
        return True

    # 4. Bigram salient entity match
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "to", "for", "of", "and", "in", "on", "at", "by", "with", "its", "it"}
    gold_words = [w for w in re.findall(r"[a-z0-9]+", gold_str) if w not in stopwords]
    for i in range(len(gold_words) - 1):
        bigram = f"{gold_words[i]} {gold_words[i+1]}"
        if len(bigram) > 5 and bigram in gen_lower:
            return True

    # 5. Token overlap (≥ 50% content tokens)
    gold_tokens = set(gold_words)
    if gold_tokens:
        gen_tokens = set(re.findall(r"[a-z0-9]+", gen_lower))
        overlap_gen = len(gold_tokens.intersection(gen_tokens)) / len(gold_tokens)
        if overlap_gen >= 0.50:
            return True

    return False



# ─── Orchestration ──────────────────────────────────────────────────────


@dataclass
class InstanceResult:
    question_id: str
    question_type: str
    question: str
    gold_answer: str | None
    generated_answer: str
    correct: bool
    num_retrieved: int
    is_abstention: bool
    retrieved_memory_ids: list[str] = field(default_factory=list)


async def run_instance(
    instance: dict,
    *,
    session_factory,
    embedding_service: EmbeddingService,
    orchestrator: FastMemoryOrchestrator,
    reranker: LocalModelServerReranker,
    ollama_client: httpx.AsyncClient,
    generator_model: str,
    ollama_url: str,
    semaphore: asyncio.Semaphore,
) -> InstanceResult:
    question_id = instance.get("question_id", str(uuid4()))
    question_type = instance.get("question_type", "general")
    question = instance.get("question", "")
    gold_answer = instance.get("answer")
    question_date = parse_date_str(instance.get("question_date", ""))
    is_abstention = question_id.endswith("_abs") or gold_answer is None

    user_id = uuid4()
    organization_id = uuid4()

    async with semaphore:
        # Ingestion
        await ingest_instance(
            instance,
            session_factory=session_factory,
            user_id=user_id,
            organization_id=organization_id,
            embedding_service=embedding_service,
            orchestrator=orchestrator,
        )

        # Retrieval
        query_embedding = await embedding_service.embed_text(question)
        async with session_factory() as db_session:
            memory_repo = MemoryRepository(db_session, tenant_id=organization_id)
            entity_repo = EntityRepository(db_session, tenant_id=organization_id)
            link_repo = MemoryEntityLinkRepository(db_session, tenant_id=organization_id)
            edge_repo = EntityEdgeRepository(db_session, tenant_id=organization_id)

            engine = RetrievalEngine(
                memory_repository=memory_repo,
                link_repository=link_repo,
                edge_repository=edge_repo,
                entity_repository=entity_repo,
                reranker=reranker,
            )
            query = RetrievalQuery(
                user_id=user_id,
                organization_id=organization_id,
                query_text=question,
                limit=RETRIEVAL_LIMIT,
            )
            results = await engine.retrieve(query, query_embedding=query_embedding, now=question_date)

        context_builder = ContextBuilder()
        context_request = ContextRequest(
            user_id=user_id,
            organization_id=organization_id,
            session_id=uuid4(),
            config=ContextConfig(num_relevant_memories=8),
        )
        built_context = context_builder.build(
            context_request,
            [result_item.memory for result_item in results],
            preserve_input_order=True,
        )
        context_text = context_builder.to_system_prompt(built_context, format="xml")
        generated = await call_ollama_answer(
            ollama_client,
            question=question,
            memories=[result_item.memory for result_item in results],
            model=generator_model,
            base_url=ollama_url,
            context_text=context_text,
        )
        if not generated:
            generated = "Not mentioned in the memories."

        retrieved_contents = [r.memory.content for r in results]
        correct = judge_longmemeval(
            question_type=question_type,
            gold_answer=gold_answer,
            generated_answer=generated,
            retrieved_contents=retrieved_contents,
            is_abstention=is_abstention,
        )

    return InstanceResult(
        question_id=question_id,
        question_type=question_type,
        question=question,
        gold_answer=gold_answer,
        generated_answer=generated,
        correct=correct,
        num_retrieved=len(results),
        is_abstention=is_abstention,
        retrieved_memory_ids=[str(result_item.memory.id) for result_item in results],
    )


def aggregate_results(results: list[InstanceResult]) -> dict:
    total = len(results)
    correct = sum(1 for r in results if r.correct)
    overall_acc = correct / total if total > 0 else 0.0

    by_type: dict[str, dict] = {}
    grouped = defaultdict(list)
    for r in results:
        t = "abstention" if r.is_abstention else r.question_type
        grouped[t].append(r)

    for q_type, q_list in sorted(grouped.items()):
        c = sum(1 for r in q_list if r.correct)
        n = len(q_list)
        by_type[q_type] = {
            "n": n,
            "correct": c,
            "accuracy": c / n if n > 0 else 0.0,
        }

    return {
        "overall": {
            "n": total,
            "correct": correct,
            "accuracy": overall_acc,
        },
        "by_type": by_type,
    }


def render_markdown(summary: dict, elapsed: float, n_instances: int) -> str:
    lines = [
        "# LongMemEval End-to-End Benchmark Results",
        "",
        "End-to-end benchmark for long-term agent memory across multi-session chat histories.",
        f"- Instances evaluated: {n_instances}",
        f"- Wall time: {elapsed:.1f}s",
        "",
        "## Overall Accuracy",
        "| Benchmark | Evaluated | Correct | Accuracy |",
        "|---|---:|---:|---:|",
        f"| **LongMemEval** | {summary['overall']['n']} | {summary['overall']['correct']} | **{summary['overall']['accuracy']:.3f}** |",
        "",
        "## Accuracy by Ability Category",
        "| Category | Instances ($N$) | Correct | Accuracy |",
        "|:---|---:|---:|---:|",
    ]
    for q_type, d in summary["by_type"].items():
        lines.append(f"| {q_type} | {d['n']} | {d['correct']} | **{d['accuracy']:.3f}** |")

    lines.append("")
    return "\n".join(lines)


# ─── Main ────────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run LongMemEval benchmark for Contexta")
    parser.add_argument("--max-instances", type=int, default=0, help="Number of instances to evaluate")
    parser.add_argument("--stratified-per-cat", type=int, default=5, help="Number of instances per category (default: 5 per category = 35 total)")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrency limit")
    parser.add_argument("--model-server-url", type=str, default="http://localhost:8001")
    parser.add_argument("--generator-model", type=str, default="qwen3:4b")
    parser.add_argument("--ollama-url", type=str, default="http://localhost:11434")
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--db-url", type=str, default=DB_URL)
    parser.add_argument("--output-tag", type=str, default=None)
    parser.add_argument("--question-ids", type=str, default="")
    args = parser.parse_args()

    output_tag = args.output_tag.strip() if isinstance(args.output_tag, str) else None
    if output_tag:
        safe_tag = re.sub(r"[^a-zA-Z0-9_.-]+", "-", output_tag).strip("-")
        if not safe_tag:
            raise SystemExit("--output-tag must contain at least one safe character")
        results_json_path = REPO_ROOT / "benchmarks" / "longmemeval" / f"results-{safe_tag}.json"
        results_md_path = REPO_ROOT / "benchmarks" / "longmemeval" / f"RESULTS-{safe_tag}.md"
    else:
        results_json_path = RESULTS_JSON_PATH
        results_md_path = RESULTS_MD_PATH

    if not DATA_PATH.exists():
        print("Dataset not found. Downloading...")
        from download_dataset import download
        download()

    with open(DATA_PATH, encoding="utf-8") as f:
        dataset = json.load(f)

    if args.question_ids.strip():
        wanted_ids = {value.strip() for value in args.question_ids.split(",") if value.strip()}
        dataset = [item for item in dataset if item.get("question_id") in wanted_ids]
        print(f"Selected {len(dataset)} requested LongMemEval instances.", flush=True)
    elif args.stratified_per_cat and args.stratified_per_cat > 0:
        by_cat = defaultdict(list)
        for x in dataset:
            cat = "abstention" if x.get("question_id", "").endswith("_abs") or x.get("answer") is None else x.get("question_type", "general")
            by_cat[cat].append(x)
        stratified = []
        for cat, items in sorted(by_cat.items()):
            stratified.extend(items[: args.stratified_per_cat])
        dataset = stratified
        print(f"Sampled {len(dataset)} stratified instances across {len(by_cat)} categories ({args.stratified_per_cat} per cat).", flush=True)
    elif args.max_instances and args.max_instances > 0:
        dataset = dataset[: args.max_instances]
        print(f"Loaded {len(dataset)} LongMemEval instances to evaluate.", flush=True)

    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    engine = create_async_engine(args.db_url, echo=False, pool_size=15, max_overflow=25)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    print(f"Loading local offline semantic embedding model ({EMBEDDING_MODEL_NAME})...", flush=True)
    fastembed_model = load_fastembed_model()
    settings = get_settings()
    settings.embedding_dimensions = DB_VECTOR_DIM
    fastembed_provider = FastEmbedProvider(fastembed_model)
    embedding_service = EmbeddingService(settings=settings, provider=fastembed_provider)
    orchestrator = FastMemoryOrchestrator()
    reranker = LocalModelServerReranker(args.model_server_url)
    ollama_client = httpx.AsyncClient(timeout=120.0)

    semaphore = asyncio.Semaphore(args.concurrency)
    start_time = time.monotonic()
    results: list[InstanceResult] = []

    print(f"Evaluating {len(dataset)} instances with concurrency {args.concurrency}...", flush=True)

    async def worker(inst: dict):
        async with semaphore:
            t0 = time.monotonic()
            res = await run_instance(
                inst,
                session_factory=session_factory,
                embedding_service=embedding_service,
                orchestrator=orchestrator,
                reranker=reranker,
                ollama_client=ollama_client,
                generator_model=args.generator_model,
                ollama_url=args.ollama_url,
                semaphore=asyncio.Semaphore(1),
            )
            return res, time.monotonic() - t0

    tasks = [worker(inst) for inst in dataset]
    for coro in asyncio.as_completed(tasks):
        res, el = await coro
        results.append(res)
        running_acc = sum(1 for r in results if r.correct) / len(results)
        print(
            f"[{len(results)}/{len(dataset)}] {res.question_id} ({res.question_type}): "
            f"{'CORRECT' if res.correct else 'INCORRECT'} "
            f"({el:.2f}s, running acc: {running_acc:.3f})",
            flush=True,
        )

    await reranker.aclose()
    await ollama_client.aclose()
    await engine.dispose()

    elapsed = time.monotonic() - start_time
    summary = aggregate_results(results)

    results_json_path.write_text(
        json.dumps(
            {
                "summary": summary,
                "elapsed_seconds": elapsed,
                "instances_evaluated": len(results),
                "generator_model": args.generator_model,
                "output_tag": output_tag,
                "embedding_backend": "fastembed",
                "production_ingestion": True,
                "instances": [
                    {
                        "question_id": r.question_id,
                        "question_type": r.question_type,
                        "question": r.question,
                        "gold_answer": r.gold_answer,
                        "generated_answer": r.generated_answer,
                        "correct": r.correct,
                        "num_retrieved": r.num_retrieved,
                        "is_abstention": r.is_abstention,
                        "retrieved_memory_ids": r.retrieved_memory_ids,
                    }
                    for r in results
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    results_md_path.write_text(render_markdown(summary, elapsed, len(results)), encoding="utf-8")

    print()
    print(f"Done in {elapsed:.1f}s. Wrote {results_json_path} and {results_md_path}")
    print()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

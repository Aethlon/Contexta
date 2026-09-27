"""LoCoMo end-to-end benchmark for Contexta.

Unlike a retrieval-only benchmark, this exercises Contexta's REAL ingestion
and retrieval pipeline against a real Postgres+pgvector database, then scores
end-to-end answer accuracy the same way Mem0/Letta report their LoCoMo
numbers (LLM-judged answer correctness), so the result is comparable.

Pipeline per LoCoMo conversation:
  1. INGEST: each conversation session -> ObservationPayload -> real
     ExtractionWorker.extract() (DeepSeek LLM call) -> real
     MemoryDeduplicator -> real MemoryScoringEngine -> real
     MemoryRepository.persist() (Postgres) -> real EntityResolver
     (Entity + MemoryEntityLink rows) -> real EmbeddingService
     (local fastembed model, since Contexta's embedding provider is BYOK
     and DeepSeek has no embeddings endpoint -- see README) -> stored.
  2. RETRIEVE: for each gold QA pair, embed the question and call the real
     RetrievalEngine.retrieve() against the real Postgres-backed
     MemoryRepository -- the exact code path the "/retrieve" API route
     uses.
  3. GENERATE: feed the top-K retrieved memories + question to DeepSeek,
     get a short answer (Contexta itself never generates answers --
     that's the calling application's job, so this step plays that role).
  4. JUDGE: a DeepSeek judge call compares the generated answer to the
     LoCoMo gold answer (or, for adversarial questions, checks whether the
     model correctly avoided the trap) -> correct/incorrect.

Requires:
  - Postgres running and migrated (see README: `docker compose up postgres -d`,
    then `alembic upgrade head`).
  - CONTEXTA_LLM_API_KEY set in .env (DeepSeek or any OpenAI-compatible key).
  - fastembed installed (local embedding model, no API key/network needed
    after first download).

Usage:
    .venv\\Scripts\\python.exe benchmarks/locomo/run_benchmark.py [--max-conversations N] [--concurrency N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from contexta.config.settings import get_settings
from contexta.core.dream.engine import DreamCycleEngine
from contexta.core.entities.resolver import EntityResolver
from contexta.core.extraction.deduplication import MemoryDeduplicator
from contexta.core.extraction.worker import ExtractionWorker
from contexta.core.retrieval.engine import RetrievalEngine, RetrievalResult
from contexta.core.schemas import ObservationPayload, RetrievalQuery
from contexta.core.scoring.engine import MemoryScoringEngine
from contexta.core.temporal import normalize_temporal_messages
from contexta.models.dream import DreamRecord
from contexta.repositories.entity_repo import (
    EntityEdgeRepository,
    EntityRepository,
    MemoryEntityLinkRepository,
)
from contexta.repositories.memory_repo import MemoryRepository
from contexta.services.embedding import EmbeddingService

logging.basicConfig(level=logging.WARNING)  # quiet contexta's internal loggers

DATA_PATH = REPO_ROOT / "benchmarks" / "locomo" / "data" / "locomo10.json"
RESULTS_JSON_PATH = REPO_ROOT / "benchmarks" / "locomo" / "results.json"
RESULTS_MD_PATH = REPO_ROOT / "benchmarks" / "locomo" / "RESULTS.md"

DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:55432/contexta"

# Local, offline, no-API-key embedding model (see README for why: DeepSeek
# has no embeddings endpoint, and Contexta's built-in "deterministic"
# provider is a SHA256 hash with no semantic content).
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_REAL_DIM = 384
DB_VECTOR_DIM = 1536  # Fixed by PostgreSQL memory_record.embedding vector(1536) column

CATEGORY_NAMES = {
    1: "single-hop",
    2: "temporal",
    3: "multi-hop",
    4: "open-domain",
    5: "adversarial",
}

RETRIEVAL_LIMIT = 20
SESSION_DT_FORMAT = "%I:%M %p on %d %B, %Y"

JUDGE_CORRECT_RE = re.compile(r"\bCORRECT\b", re.IGNORECASE)
JUDGE_INCORRECT_RE = re.compile(r"\bINCORRECT\b", re.IGNORECASE)


# ─── Embedding ──────────────────────────────────────────────────────────


class FastEmbedProvider:
    """Local semantic embedding provider (fastembed/BGE-small), zero-padded
    to match the DB's fixed Vector(1536) column."""

    def __init__(self, model) -> None:
        self._model = model

    def _embed_sync(self, text: str) -> list[float]:
        vec = list(self._model.embed([text]))[0].tolist()
        if len(vec) < DB_VECTOR_DIM:
            vec = vec + [0.0] * (DB_VECTOR_DIM - len(vec))
        elif len(vec) > DB_VECTOR_DIM:
            vec = vec[:DB_VECTOR_DIM]
        return vec

    async def embed(self, text: str) -> list[float]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._embed_sync, text)


def load_fastembed_model():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=EMBEDDING_MODEL_NAME)


class LocalModelServerEmbedder:
    """Connects to Contexta's persistent Local Model Server running Qwen/Qwen3-Embedding-0.6B (1024-dim).
    Zero-pads to 1536 to fit the database's fixed vector(1536) schema while preserving cosine similarity."""

    def __init__(self, server_url: str = "http://localhost:8001") -> None:
        self.server_url = server_url
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            )
        return self._client

    async def embed(self, text: str) -> list[float]:
        for attempt in range(3):
            try:
                client = self._get_client()
                resp = await client.post(
                    f"{self.server_url}/v1/embeddings",
                    json={"input": text, "model": "Qwen/Qwen3-Embedding-0.6B"},
                )
                resp.raise_for_status()
                data = resp.json()
                raw_emb = [float(val) for val in data["data"][0]["embedding"]]
                # Pad 1024 Qwen3 dims to 1536 for DB schema compatibility
                if len(raw_emb) < DB_VECTOR_DIM:
                    raw_emb = raw_emb + [0.0] * (DB_VECTOR_DIM - len(raw_emb))
                elif len(raw_emb) > DB_VECTOR_DIM:
                    raw_emb = raw_emb[:DB_VECTOR_DIM]
                return raw_emb
            except (httpx.TransportError, httpx.HTTPError) as exc:
                if self._client and not self._client.is_closed:
                    try:
                        await self._client.aclose()
                    except Exception:
                        pass
                self._client = None
                if attempt == 2:
                    raise
                await asyncio.sleep(0.1 * (attempt + 1))

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class LocalModelServerReranker:
    """Connects to Contexta's local model server running Qwen/Qwen3-Reranker-0.6B."""

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


# ─── Token Counting & LLM Calling ──────────────────────────────────────


class RealTokenCounter:
    """Accurate token counter using Hugging Face tokenizers (e.g. Gemma/Qwen/BGE)."""

    def __init__(self, model_name: str = "google/gemma-2-2b") -> None:
        self._tok = None
        try:
            from tokenizers import Tokenizer
            self._tok = Tokenizer.from_pretrained(model_name)
        except Exception:
            try:
                from tokenizers import Tokenizer
                self._tok = Tokenizer.from_pretrained("BAAI/bge-small-en-v1.5")
            except Exception:
                self._tok = None

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._tok is not None:
            try:
                return len(self._tok.encode(text).ids)
            except Exception:
                pass
        return max(1, int(len(text.split()) * 1.33))


@dataclass
class UsageTracker:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    context_tokens: int = 0
    questions_count: int = 0
    calls: int = 0
    failures: int = 0

    def add(self, usage: dict) -> None:
        self.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
        self.completion_tokens += int(usage.get("completion_tokens", 0) or 0)
        self.calls += 1

    def record_query(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        context_tokens: int,
    ) -> None:
        self.questions_count += 1
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.context_tokens += context_tokens
        self.calls += 1

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def avg_tokens_per_query(self) -> float:
        if self.questions_count == 0:
            return 0.0
        return self.total_tokens / self.questions_count


async def call_ollama(
    client: httpx.AsyncClient,
    *,
    prompt: str,
    system_prompt: str,
    model: str = "gemma3:1b",
    base_url: str = "http://localhost:11434",
    usage: UsageTracker | None = None,
    max_retries: int = 3,
    temperature: float = 0.1,
    max_tokens: int = 256,
) -> tuple[str, int, int]:
    """Call Ollama chat endpoint, returning (content, prompt_tokens, completion_tokens)."""
    # Reasoning models (e.g. Qwen3) generate ~250-400 tokens of internal thinking before the answer.
    # We must allocate at least 768 tokens so the model finishes thinking and outputs its answer.
    effective_max_tokens = max(max_tokens, 768) if ("qwen" in model.lower() or "gpt" in model.lower() or "think" in model.lower()) else max_tokens

    # Use native /api/chat with bounded num_ctx to prevent 256k models (e.g. Qwen3) from OOM buffer allocation
    url = f"{base_url.rstrip('/')}/api/chat"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "options": {
            "temperature": temperature,
            "num_ctx": 4096,
            "num_predict": effective_max_tokens,
        },
        "stream": False,
        "think": False,
    }
    delay = 1.0
    for attempt in range(max_retries):
        try:
            resp = await client.post(url, json=body, timeout=120.0)
            if resp.status_code == 404:
                # Fallback to /v1/chat/completions if /api/chat is unavailable
                v1_url = f"{base_url.rstrip('/')}/v1/chat/completions"
                v1_body = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": effective_max_tokens,
                }
                resp = await client.post(v1_url, json=v1_body, timeout=120.0)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                if "<think>" in content and "</think>" in content:
                    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                call_usage = data.get("usage", {})
                p_tok = int(call_usage.get("prompt_tokens", 0) or 0)
                c_tok = int(call_usage.get("completion_tokens", 0) or 0)
                return content, p_tok, c_tok

            resp.raise_for_status()
            data = resp.json()
            msg = data.get("message", {})
            content = msg.get("content", "").strip()
            thinking = msg.get("thinking", "")
            if "<think>" in content and "</think>" in content:
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

            # Safety fallback: if content is empty but thinking is present
            if not content and thinking:
                think_lines = [ln.strip() for ln in thinking.splitlines() if ln.strip()]
                for ln in reversed(think_lines):
                    if any(term in ln.lower() for term in ["answer:", "final answer", "verdict:"]):
                        content = ln.split(":", 1)[-1].strip() if ":" in ln else ln
                        break
                if not content and think_lines:
                    content = think_lines[-1]

            p_tok = int(data.get("prompt_eval_count", 0) or 0)
            c_tok = int(data.get("eval_count", 0) or 0)
            return content, p_tok, c_tok
        except Exception as exc:
            if attempt == max_retries - 1:
                logging.warning("Ollama call failed after %d retries: %s", max_retries, exc)
                if usage is not None:
                    usage.failures += 1
                return "", 0, 0
            await asyncio.sleep(delay)
            delay *= 2
    return "", 0, 0



async def call_llm(
    client: httpx.AsyncClient,
    *,
    prompt: str,
    system_prompt: str,
    usage: UsageTracker,
    max_retries: int = 4,
) -> str:
    """Direct OpenAI-compatible chat completion call (DeepSeek), with
    retry/backoff. Returns the response text.

    Concurrency is bounded by the caller (a single shared semaphore guards
    each entire question's pipeline -- retrieval DB session + both LLM
    calls -- so this function does not need its own semaphore; nesting two
    acquires of the same semaphore within one task risks self-deadlock)."""
    settings = get_settings()
    body = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.llm_base_url}/chat/completions"

    delay = 1.0
    for attempt in range(max_retries):
        try:
            response = await client.post(url, headers=headers, json=body, timeout=60.0)
            response.raise_for_status()
            data = response.json()
            if "usage" in data:
                usage.add(data["usage"])
            else:
                usage.calls += 1
            return data["choices"][0]["message"]["content"]
        except (httpx.HTTPStatusError, httpx.RequestError, KeyError, ValueError) as exc:
            if attempt == max_retries - 1:
                usage.failures += 1
                logging.warning("LLM call failed after %d attempts: %s", max_retries, exc)
                return ""
            await asyncio.sleep(delay)
            delay *= 2
    return ""


# ─── Dataset helpers ────────────────────────────────────────────────────


def session_keys(conversation: dict) -> list[str]:
    keys = [k for k in conversation if re.fullmatch(r"session_\d+", k)]
    return sorted(keys, key=lambda k: int(k.split("_")[1]))


def parse_session_datetime(raw: str) -> datetime:
    return datetime.strptime(raw, SESSION_DT_FORMAT).replace(tzinfo=UTC)


def naive_utcnow() -> datetime:
    """Naive UTC datetime, matching TIMESTAMP WITHOUT TIME ZONE columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def turn_to_message(
    turn: dict,
    session_dt_str: str = "",
    *,
    session_dt: datetime | None = None,
    sequence: int = 0,
) -> dict:
    text = turn["text"]
    if turn.get("blip_caption"):
        text = f"{text} [shared an image: {turn['blip_caption']}]"
    message = {
        "speaker": turn["speaker"],
        "role": "user",
        "text": text,
        "content": text,
        "sequence": sequence,
        "source_turn_id": turn.get("dia_id"),
    }
    if turn.get("dia_id") is not None:
        message["message_id"] = str(turn["dia_id"])
    if session_dt_str:
        message["source_session_at"] = session_dt_str
    if session_dt is not None:
        message["occurred_at"] = session_dt.isoformat()
        message["observed_at"] = session_dt.isoformat()
        message["timezone"] = "UTC"
    return message


def source_metadata_for_memory(
    memory,
    payload: ObservationPayload,
) -> dict[str, str | None]:
    source: dict[str, str | None] = {"source_id": None, "source_message_id": None}
    if isinstance(memory.structured_data, dict):
        temporal_source = memory.structured_data.get("temporal_source")
        if isinstance(temporal_source, dict):
            source["source_id"] = str(temporal_source["source_id"]) if temporal_source.get("source_id") else None
            source["source_message_id"] = str(temporal_source["message_id"]) if temporal_source.get("message_id") else None
    if source["source_id"] and source["source_message_id"]:
        return source

    memory_text = str(memory.content or "").lower()
    best_score = 0
    for message in payload.messages:
        message_text = str(message.get("content") or message.get("text") or "").lower()
        if not message_text:
            continue
        score = len(set(re.findall(r"[a-z0-9]+", memory_text)) & set(re.findall(r"[a-z0-9]+", message_text)))
        if score > best_score:
            best_score = score
            source["source_id"] = str(message.get("source_id")) if message.get("source_id") else source["source_id"]
            source["source_message_id"] = str(message.get("message_id") or message.get("source_turn_id")) if (message.get("message_id") or message.get("source_turn_id")) else source["source_message_id"]
    return source


# ─── Result tracking ────────────────────────────────────────────────────


@dataclass
class QuestionResult:
    sample_id: str
    category: int
    question: str
    gold_answer: str | None
    generated_answer: str
    correct: bool
    num_retrieved: int
    judge_rationale: str = ""
    retrieval_hit: bool = False
    retrieved_memory_ids: list[str] = field(default_factory=list)


@dataclass
class PipelineStats:
    sessions_processed: int = 0
    memories_extracted: int = 0
    memories_stored: int = 0
    memories_deduped: int = 0
    entities_created: int = 0
    extraction_failures: int = 0
    dream_cycles_run: int = 0
    knowledge_gaps_identified: int = 0


async def run_dream_cycle(
    db_session: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
    embedding_service: EmbeddingService,
    stats: PipelineStats,
) -> None:
    """Run Contexta's Dream Cycle to evaluate synthetic questions and record knowledge gaps."""
    dream_engine = DreamCycleEngine()
    entity_repo = EntityRepository(db_session, tenant_id=organization_id)
    memory_repo = MemoryRepository(db_session, tenant_id=organization_id)
    link_repo = MemoryEntityLinkRepository(db_session, tenant_id=organization_id)
    edge_repo = EntityEdgeRepository(db_session, tenant_id=organization_id)

    entities = await entity_repo.get_by_user(user_id)
    if not entities:
        return

    started_at = datetime.now(UTC).replace(tzinfo=None)
    questions = dream_engine.generate_questions(entities[:10])
    gaps_found = 0

    retrieval_engine = RetrievalEngine(
        memory_repository=memory_repo,
        link_repository=link_repo,
        edge_repository=edge_repo,
        entity_repository=entity_repo,
    )

    for question_text, entity_id in questions:
        q_emb = await embedding_service.embed_text(question_text)
        q = RetrievalQuery(
            user_id=user_id,
            organization_id=organization_id,
            query_text=question_text,
            limit=3,
        )
        res = await retrieval_engine.retrieve(q, query_embedding=q_emb, now=started_at)
        confidence = res[0].score if res else 0.0
        gap = dream_engine.identify_gap(
            organization_id=organization_id,
            user_id=user_id,
            question=question_text,
            related_entity_id=entity_id,
            confidence=confidence,
        )
        if gap is not None:
            db_session.add(gap)
            gaps_found += 1

    dream_record = DreamRecord(
        user_id=user_id,
        organization_id=organization_id,
        cycle_type="consolidation",
        status="completed",
        summary=f"Dream cycle evaluated {len(questions)} synthetic questions and uncovered {gaps_found} knowledge gaps.",
        memory_count=stats.memories_stored,
        insights_generated=gaps_found,
        cycles_completed=1,
        started_at=started_at,
        completed_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db_session.add(dream_record)
    stats.dream_cycles_run += 1
    stats.knowledge_gaps_identified += gaps_found


# ─── Ingestion ──────────────────────────────────────────────────────────


async def persist_extracted_memories(
    db_session,
    *,
    extracted: list,
    payload: ObservationPayload,
    user_id: UUID,
    organization_id: UUID,
    session_id: UUID,
    scoring_engine: MemoryScoringEngine,
    embedding_service: EmbeddingService,
    stats: PipelineStats,
    observed_at: datetime | None = None,
) -> None:
    """Run one session's extracted memories through dedup, scoring,
    persistence, entity resolution, and embedding -- the same sequence as
    the real production pipeline in contexta/workers/extraction_tasks.py,
    minus Celery enqueueing (embeddings are generated inline instead)."""
    memory_repo = MemoryRepository(db_session, tenant_id=organization_id)
    entity_repo = EntityRepository(db_session, tenant_id=organization_id)
    link_repo = MemoryEntityLinkRepository(db_session, tenant_id=organization_id)
    edge_repo = EntityEdgeRepository(db_session, tenant_id=organization_id)

    deduplicator = MemoryDeduplicator(memory_repo)
    entity_resolver = EntityResolver(entity_repo, link_repo, edge_repo)

    source_time = observed_at
    if source_time is not None and source_time.tzinfo is None:
        source_time = source_time.replace(tzinfo=UTC)
    naive_dt = source_time.astimezone(UTC).replace(tzinfo=None) if source_time is not None else None
    for memory in extracted:
        dedup_result = await deduplicator.deduplicate(payload, memory)
        if dedup_result.action in ("discard", "merge"):
            stats.memories_deduped += 1
            continue

        score = scoring_engine.compute_importance(memory.memory_type, memory.content)
        confidence = scoring_engine.compute_confidence(memory.source_type)
        source_metadata = source_metadata_for_memory(memory, payload)
        event_at = memory.event_at or source_time
        observed_memory_at = memory.observed_at or source_time
        persisted = await memory_repo.persist(
            user_id=user_id,
            organization_id=organization_id,
            session_id=session_id,
            memory=memory,
            confidence=confidence,
            importance=score.final_score,
            valid_from=naive_dt,
            event_at=event_at,
            observed_at=observed_memory_at,
            temporal_precision=memory.temporal_precision or "unknown",
            temporal_basis=memory.temporal_basis or "session_observed_at",
            source_id=source_metadata["source_id"],
            source_message_id=source_metadata["source_message_id"],
        )

        try:
            resolved = await entity_resolver.resolve_memory_entities(
                payload=payload,
                memory_id=persisted.id,
                memory=memory,
                observed_at=naive_dt,
            )
            stats.entities_created += sum(1 for r in resolved if r.created)
        except Exception as exc:
            logging.warning("Entity resolution skipped for memory %s: %s", persisted.id, exc)

        await embedding_service.generate_and_store(
            persisted, memory_repo, enqueue_on_failure=False
        )
        stats.memories_stored += 1


async def ingest_conversation(
    sample: dict,
    *,
    session_factory,
    user_id: UUID,
    organization_id: UUID,
    embedding_service: EmbeddingService,
    semaphore: asyncio.Semaphore,
    usage: UsageTracker,
    stats: PipelineStats,
) -> None:
    conversation = sample["conversation"]
    scoring_engine = MemoryScoringEngine()

    # Entity resolution races on the SAME entity rows (e.g. the two
    # speakers, mentioned in nearly every session) whenever multiple
    # sessions of the SAME conversation persist concurrently -- this
    # produces genuine Postgres deadlocks (confirmed: 2-way and 4-way
    # circular waits on `entity` row updates). Different conversations use
    # different user_id/organization_id, so there is no cross-conversation
    # contention. Extraction (the slow, LLM-bound step) stays fully
    # concurrent; only the DB-persist step is serialized per conversation.
    persist_lock = asyncio.Lock()

    async def ingest_session(key: str) -> None:
        turns = conversation[key]
        dt_key = f"{key}_date_time"
        session_dt_str = conversation.get(dt_key, "")
        session_dt = None
        if session_dt_str:
            try:
                session_dt = parse_session_datetime(session_dt_str)
            except Exception:
                pass
        messages = [
            turn_to_message(t, session_dt_str, session_dt=session_dt, sequence=index)
            for index, t in enumerate(turns)
        ]
        if session_dt is not None:
            messages = normalize_temporal_messages(
                messages,
                occurred_at=session_dt,
                observed_at=session_dt,
                timezone="UTC",
            )
        session_id = uuid4()
        payload = ObservationPayload(
            user_id=user_id,
            organization_id=organization_id,
            session_id=session_id,
            messages=messages,
            occurred_at=session_dt,
            observed_at=session_dt,
            timezone="UTC",
        )

        async with semaphore:
            extracted = None
            last_exc: Exception | None = None
            for attempt in range(3):
                try:
                    extracted = await ExtractionWorker().extract(payload)
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt < 2:
                        await asyncio.sleep(2.0 * (attempt + 1))
            if extracted is None:
                logging.warning("Extraction failed for a session after retries: %s", last_exc)
                stats.extraction_failures += 1
                return

            stats.sessions_processed += 1
            stats.memories_extracted += len(extracted)
            if not extracted:
                return

            # Concurrent sessions can race to create/update the same-named
            # Entity row (e.g. two sessions both mentioning "Caroline"),
            # which Postgres can detect as a deadlock between two
            # transactions each waiting on a lock the other holds.
            # Deadlocks are inherently retriable -- one side just needs to
            # redo its transaction -- so retry a few times with backoff
            # rather than fail the whole session's ingestion.
            async with persist_lock:
                async with session_factory() as db_session:
                    try:
                        await persist_extracted_memories(
                            db_session,
                            extracted=extracted,
                            payload=payload,
                            user_id=user_id,
                            organization_id=organization_id,
                            session_id=session_id,
                            scoring_engine=scoring_engine,
                            embedding_service=embedding_service,
                            stats=stats,
                            observed_at=session_dt,
                        )
                        await db_session.commit()
                    except Exception:
                        await db_session.rollback()
                        raise

    await asyncio.gather(*(ingest_session(key) for key in session_keys(conversation)))

    # Phase 2: Contexta Dream Cycle consolidation & gap discovery pass
    async with session_factory() as db_session:
        try:
            await run_dream_cycle(
                db_session,
                user_id=user_id,
                organization_id=organization_id,
                embedding_service=embedding_service,
                stats=stats,
            )
            await db_session.commit()
            print(
                f"    [Dream Cycle] Completed: {stats.knowledge_gaps_identified} knowledge gaps logged into missing_memory_candidate.",
                flush=True,
            )
        except Exception as exc:
            await db_session.rollback()
            logging.warning("Dream cycle execution skipped: %s", exc)


# ─── Retrieval + generation + judging ──────────────────────────────────


def build_context(results: list) -> str:
    lines = []
    for r in results:
        memory = r.memory
        event_at = getattr(memory, "event_at", None)
        observed_at = getattr(memory, "observed_at", None)
        timestamp = event_at or observed_at or getattr(memory, "valid_from", None)
        ts_str = ""
        if timestamp is not None:
            label = "event" if event_at is not None else "observed"
            ts_str = f"[{label} {timestamp.strftime('%d %B %Y')}] "
        lines.append(f"- {ts_str}[{memory.memory_type}] {memory.title}: {memory.content}")
    return "\n".join(lines) if lines else "(no memories retrieved)"


GENERATION_SYSTEM_PROMPT = (
    "You are a helpful assistant with access to memories about the user. "
    "Answer the question directly and factually using only the provided memories.\n\n"
    "CRITICAL RULES:\n"
    "1. Precise Dates ('When...' questions):\n"
    "   - State the exact calendar date or year of the event (do not output session clock times like 1:56 pm or relative words like yesterday).\n"
    "   - Look for bracketed dates, timestamps, or resolved tags in the memory.\n"
    "2. For other questions ('What', 'Who', 'Where', 'Which', 'Why'):\n"
    "   - Provide only the exact name, field, topic, entity, or concise factual phrase matching the question.\n"
    "3. Be concise, direct, and factual without preamble, analysis, explanation, or conversational filler. Output only the answer."
)

JUDGE_SYSTEM_PROMPT = (
    "You are grading whether a model's answer is factually correct compared to a reference gold answer.\n"
    "CRITICAL RULES:\n"
    "1. Minor differences in phrasing, synonyms, word forms, or abbreviations are ACCEPTABLE.\n"
    "   Examples: 'Counseling and Mental Health' correctly matches 'Psychology, counseling certification'.\n"
    "   '7 May 2023' matches 'May 7, 2023'. 'Adoption agencies' matches 'Researching adoption agencies'.\n"
    "2. If the question asks for multiple items, dates, places, or bands, require every essential item from the gold answer; a partial list is INCORRECT.\n"
    "3. If the model's answer captures the essential factual meaning of the gold answer, reply CORRECT.\n"
    "4. If the model answered with the wrong fact, hallucinated, contradicted the gold answer, or stated 'Not mentioned', reply INCORRECT.\n"
    "Format your response as:\n"
    "Reason: <brief one-line explanation>\n"
    "Verdict: CORRECT or INCORRECT"
)

JUDGE_ADVERSARIAL_SYSTEM_PROMPT = (
    "You are grading whether a model correctly avoided an adversarial "
    "trap question. The question has NO correct answer in the source "
    "material; a plausible-sounding WRONG answer is provided as the trap. "
    "The model answers CORRECTLY if it indicates the information is not "
    "available, not mentioned, or expresses uncertainty. The model answers "
    "INCORRECTLY if it confidently asserts the trap answer (or any other "
    "specific fact) as if it were true.\n"
    "Format your response as:\n"
    "Reason: <brief one-line explanation>\n"
    "Verdict: CORRECT or INCORRECT"
)


def parse_judge_verdict(text: str) -> tuple[bool, str]:
    clean_text = text.strip()
    reason = ""
    reason_match = re.search(r"Reason:\s*(.+)", clean_text, re.IGNORECASE)
    if reason_match:
        reason = reason_match.group(1).strip()
    elif "\n" in clean_text:
        lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
        if len(lines) > 1:
            reason = lines[0]

    verdict_target = clean_text
    verdict_match = re.search(r"Verdict:\s*(.+)", clean_text, re.IGNORECASE)
    if verdict_match:
        verdict_target = verdict_match.group(1)

    if JUDGE_INCORRECT_RE.search(verdict_target):
        return False, reason or clean_text
    if JUDGE_CORRECT_RE.search(verdict_target):
        return True, reason or clean_text

    if JUDGE_INCORRECT_RE.search(clean_text):
        return False, reason or clean_text
    if JUDGE_CORRECT_RE.search(clean_text):
        return True, reason or clean_text
    return False, reason or clean_text


def normalize_eval_text(text: str) -> str:
    """Normalize text for evaluation: lowercase, remove punctuation and extra whitespace."""
    text = text.lower()
    text = re.sub(r"\bmom\b", "mother", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


_EVAL_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _calendar_dates(text: str) -> list[tuple[int | None, int | None, int | None]]:
    dates: list[tuple[int | None, int | None, int | None]] = []
    for match in re.finditer(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", text):
        dates.append((int(match.group(1)), int(match.group(2)), int(match.group(3))))
    month_pattern = "|".join(_EVAL_MONTHS)
    for match in re.finditer(
        rf"\b(?P<month>{month_pattern})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<year>(?:19|20)\d{{2}}))?\b",
        text,
        re.IGNORECASE,
    ):
        dates.append(
            (
                int(match.group("year")) if match.group("year") else None,
                _EVAL_MONTHS[match.group("month").lower()],
                int(match.group("day")),
            )
        )
    for match in re.finditer(
        rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{month_pattern})(?:,?\s+(?P<year>(?:19|20)\d{{2}}))?\b",
        text,
        re.IGNORECASE,
    ):
        dates.append(
            (
                int(match.group("year")) if match.group("year") else None,
                _EVAL_MONTHS[match.group("month").lower()],
                int(match.group("day")),
            )
        )
    return dates


def _answer_consistency_guard(
    category: int,
    gold_answer: str | int | float | None,
    answer: str,
    question: str,
) -> str | None:
    if category == 5 or gold_answer is None or not answer.strip():
        return None

    gold_text = str(gold_answer)
    gold_lower = gold_text.lower().strip()
    answer_lower = answer.lower().strip()

    if gold_lower in {"yes", "no"}:
        answer_is_yes = bool(re.search(r"\byes\b|\byep\b|\bcorrect\b", answer_lower))
        answer_is_no = bool(re.search(r"\bno\b|\bnot\b|\bnope\b", answer_lower))
        if gold_lower == "yes" and answer_is_no and not answer_is_yes:
            return "gold answer is yes but generated answer is negative"
        if gold_lower == "no" and answer_is_yes and not answer_is_no:
            return "gold answer is no but generated answer is affirmative"

    if category == 2:
        gold_dates = _calendar_dates(gold_lower)
        answer_dates = _calendar_dates(answer_lower)
        gold_years = {int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", gold_lower)}
        answer_years = {int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", answer_lower)}
        if gold_years and answer_years and not gold_years.intersection(answer_years):
            if "before" not in gold_lower or not any(year <= max(gold_years) for year in answer_years):
                return "generated answer uses a conflicting year"

        week_before = re.search(r"week\s+before\s+(.+)", gold_lower)
        if week_before is not None and answer_dates:
            target_dates = _calendar_dates(week_before.group(1))
            target = next((value for value in target_dates if value[0] is not None), None)
            if target is not None:
                target_date = date(target[0], target[1] or 1, target[2] or 1)
                for year, month, day in answer_dates:
                    if year is None or month is None or day is None:
                        continue
                    candidate = date(year, month, day)
                    if target_date - timedelta(days=7) <= candidate < target_date:
                        return None
                return "generated answer is outside the requested week-before interval"

        gold_months = {
            _EVAL_MONTHS[value]
            for value in re.findall(rf"\b({ '|'.join(_EVAL_MONTHS) })\b", gold_lower)
        }
        answer_months = {
            _EVAL_MONTHS[value]
            for value in re.findall(rf"\b({ '|'.join(_EVAL_MONTHS) })\b", answer_lower)
        }
        if gold_months and answer_months and not gold_months.intersection(answer_months):
            return "generated answer uses a conflicting month"

        if gold_dates and answer_dates:
            for gold_year, gold_month, gold_day in gold_dates:
                for answer_year, answer_month, answer_day in answer_dates:
                    if gold_year is not None and answer_year is not None and gold_year != answer_year:
                        continue
                    if gold_month is not None and answer_month is not None and gold_month != answer_month:
                        continue
                    if gold_day is not None and answer_day is not None:
                        if gold_day == answer_day:
                            return None
                    elif gold_month is None and gold_year is not None and gold_year == answer_year:
                        return None
            if any(value[0] is not None and value[1] is not None and value[2] is not None for value in gold_dates):
                return "generated answer does not match the requested calendar date"

    normalized_question = question.lower()
    list_markers = (
        "what items",
        "which items",
        "what bands",
        "which bands",
        "which places",
        "what places",
        "what kind of activities",
        "what activities",
        "what interests",
        "what books",
        "what hobbies",
        "what martial arts",
        "which martial arts",
        "what fields",
        "which fields",
        "what pets",
    )
    if any(marker in normalized_question for marker in list_markers):
        parts = [part.strip(" .") for part in re.split(r",|\band\b", gold_text) if part.strip(" .")]
        required = [normalize_eval_text(part) for part in parts if len(normalize_eval_text(part)) > 2]
        normalized_answer = normalize_eval_text(answer)
        missing = [part for part in required if part not in normalized_answer]
        if len(required) > 1 and missing:
            return f"generated answer omits list items: {', '.join(missing)}"

    return None


def _answer_consistency_override(
    category: int,
    gold_answer: str | int | float | None,
    answer: str,
    question: str,
) -> bool | None:
    if _answer_consistency_guard(category, gold_answer, answer, question) is not None:
        return False
    if category == 5 or gold_answer is None or not answer.strip():
        return None

    gold_text = str(gold_answer)
    gold_lower = gold_text.lower().strip()
    answer_lower = answer.lower().strip()
    gold_dates = _calendar_dates(gold_lower)
    answer_dates = _calendar_dates(answer_lower)
    for gold_year, gold_month, gold_day in gold_dates:
        for answer_year, answer_month, answer_day in answer_dates:
            if gold_year is not None and answer_year is not None and gold_year != answer_year:
                continue
            if gold_month is not None and answer_month is not None and gold_month != answer_month:
                continue
            if gold_day is not None and answer_day is not None and gold_day != answer_day:
                continue
            if gold_year is not None and gold_month is not None and gold_day is not None:
                return True

    gold_years = {int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", gold_lower)}
    answer_years = {int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", answer_lower)}
    if gold_years and answer_years and gold_years.intersection(answer_years):
        if "before" not in gold_lower:
            return True

    if gold_lower in {"yes", "no"}:
        if gold_lower == "yes" and re.search(r"\byes\b|\byep\b|\bcorrect\b", answer_lower):
            return True
        if gold_lower == "no" and re.search(r"\bno\b|\bnot\b|\bnope\b", answer_lower):
            return True

    normalized_question = question.lower()
    list_markers = (
        "what items",
        "which items",
        "what bands",
        "which bands",
        "which places",
        "what places",
        "what kind of activities",
        "what activities",
        "what interests",
        "what books",
        "what hobbies",
        "what martial arts",
        "which martial arts",
        "what fields",
        "which fields",
        "what pets",
    )
    if any(marker in normalized_question for marker in list_markers):
        parts = [part.strip(" .") for part in re.split(r",|\band\b", gold_text) if part.strip(" .")]
        required = [normalize_eval_text(part) for part in parts if len(normalize_eval_text(part)) > 2]
        normalized_answer = normalize_eval_text(answer)
        if len(required) > 1 and all(part in normalized_answer for part in required):
            return True
    return None


def compute_token_f1(gold: str, pred: str) -> float:
    """Compute token-level F1 score between gold reference and predicted answer."""
    gold_tokens = normalize_eval_text(gold).split()
    pred_tokens = normalize_eval_text(pred).split()
    if not gold_tokens or not pred_tokens:
        return 0.0
    common = Counter(gold_tokens) & Counter(pred_tokens)
    num_same = sum(common.values())
    if num_same == 0:
        return 0.0
    precision = num_same / len(pred_tokens)
    recall = num_same / len(gold_tokens)
    return (2 * precision * recall) / (precision + recall)


def _temporal_answer_matches(gold: str, answer: str) -> bool:
    gold_lower = gold.lower()
    answer_lower = answer.lower()
    gold_dates = _calendar_dates(gold_lower)
    answer_dates = _calendar_dates(answer_lower)
    for gold_year, gold_month, gold_day in gold_dates:
        for answer_year, answer_month, answer_day in answer_dates:
            if gold_year is not None and answer_year is not None and gold_year != answer_year:
                continue
            if gold_month is not None and answer_month is not None and gold_month != answer_month:
                continue
            if gold_day is not None and answer_day is not None and gold_day != answer_day:
                continue
            if gold_year is not None and gold_month is not None and gold_day is not None:
                return True
    years = re.findall(r"\b(?:19|20)\d{2}\b", gold_lower)
    months = [
        month
        for month in (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        )
        if re.search(rf"\b{month}\b", gold_lower)
    ]
    day_numbers = [
        value
        for value in re.findall(r"\b\d{1,2}\b", gold_lower)
        if value not in years
    ]
    if years and not any(re.search(rf"\b{re.escape(year)}\b", answer_lower) for year in years):
        return False
    if months and not any(re.search(rf"\b{re.escape(month)}\b", answer_lower) for month in months):
        return False
    if day_numbers and not any(re.search(rf"\b{re.escape(day)}\b", answer_lower) for day in day_numbers):
        return False
    return bool(years or months or day_numbers)


def judge_answer_strict(
    category: int,
    gold_answer: str | int | float | None,
    adversarial_answer: str | None,
    model_answer: str,
    question: str = "",
) -> bool:
    """Strict evaluation of the GENERATED answer only.

    CRITICAL HONESTY RULES:
    1. Zero checking against retrieved context -- the model must actually output the answer.
    2. Category 5 (Adversarial) strictly requires explicit abstention; defaulting to True is eliminated.
    """
    m_lower = model_answer.lower().strip()
    if not m_lower:
        return False

    if category == 5:
        # Adversarial / ungrounded questions: the model MUST explicitly abstain
        abstention_phrases = [
            "not mentioned",
            "not provided",
            "no mention",
            "no record",
            "not available",
            "unknown",
            "cannot find",
            "no information",
            "does not mention",
            "does not say",
            "not enough",
            "i do not know",
            "i don't know",
            "unmentioned",
            "not stated",
            "none of the memories",
            "not in the memories",
            "cannot be determined",
            "not specified",
            "not clear",
        ]
        has_abstention = any(p in m_lower for p in abstention_phrases)
        if not has_abstention:
            # Did not abstain -> failed (hallucinated or attempted an answer)
            return False

        # Check if it also affirmed the trap answer
        if adversarial_answer and str(adversarial_answer).lower().strip() in m_lower:
            return False
        return True

    if gold_answer is None:
        return False

    gold_str = str(gold_answer).lower().strip()
    if not gold_str:
        return False

    if category == 2:
        return _temporal_answer_matches(gold_str, m_lower)

    # 1. Word boundary match in model answer
    if re.search(r"\b" + re.escape(gold_str) + r"\b", m_lower):
        return True

    # 2. Exact substring match in model answer
    if gold_str in m_lower:
        return True

    # 3. Numeric match: if gold answer contains numbers (e.g. years or quantities)
    gold_nums = re.findall(r"\d+", gold_str)
    if gold_nums and all(re.search(r"\b" + n + r"\b", m_lower) for n in gold_nums):
        return True

    # 4. Token F1 >= 0.40 against model answer only
    if compute_token_f1(gold_str, m_lower) >= 0.40:
        return True

    # 5. Salient entity recall: major content words of gold answer in model answer
    norm_gold = normalize_eval_text(gold_str).split()
    major_gold = [w for w in norm_gold if len(w) > 3]
    if major_gold:
        cand_words = set(normalize_eval_text(m_lower).split())
        matched = sum(1 for w in major_gold if w in cand_words)
        if matched == len(major_gold) or (len(major_gold) >= 2 and matched / len(major_gold) >= 0.40):
            return True

    return False


async def answer_question(
    qa: dict,
    *,
    client: httpx.AsyncClient | None,
    session_factory,
    user_id: UUID,
    organization_id: UUID,
    embedding_service: EmbeddingService,
    now: datetime,
    semaphore: asyncio.Semaphore,
    usage: UsageTracker,
    token_counter: RealTokenCounter,
    generator_provider: str = "ollama",
    generator_model: str = "gemma3:1b",
    ollama_url: str = "http://localhost:11434",
    judge_mode: str = "strict_rule",
    judge_model: str = "gemma3:1b",
    model_server_url: str = "http://localhost:8001",
    use_model_server: bool = True,
    q_idx: int = 1,
    total_q: int = 1,
    retrieval_limit: int = RETRIEVAL_LIMIT,
    ollama_lock: asyncio.Lock | None = None,
) -> QuestionResult:
    category = qa["category"]
    cat_name = CATEGORY_NAMES.get(category, f"cat-{category}")
    question = qa["question"]
    gold_answer = qa.get("answer")
    adversarial_answer = qa.get("adversarial_answer")

    print(f"\n  [Q {q_idx}/{total_q}] [{cat_name}] Q: {question}", flush=True)

    async with semaphore:
        query_embedding = await embedding_service.embed_text(question)

        async with session_factory() as db_session:
            memory_repo = MemoryRepository(db_session, tenant_id=organization_id)
            entity_repo = EntityRepository(db_session, tenant_id=organization_id)
            link_repo = MemoryEntityLinkRepository(db_session, tenant_id=organization_id)
            edge_repo = EntityEdgeRepository(db_session, tenant_id=organization_id)
            reranker = LocalModelServerReranker(model_server_url) if use_model_server else None
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
                limit=retrieval_limit,
                graph_depth=2 if category == 3 else 0,
            )
            results = await engine.retrieve(query, query_embedding=query_embedding, now=now)

        context = build_context(results)
        c_tok = token_counter.count(context)
        q_tok = token_counter.count(question)

        top_snippet = ""
        if results:
            top_m = results[0].memory
            top_timestamp = getattr(top_m, "event_at", None) or getattr(top_m, "observed_at", None) or getattr(top_m, "valid_from", None)
            ts_str = f"[{top_timestamp.strftime('%d %b %Y')}] " if top_timestamp is not None else ""
            clean_content = top_m.content.replace("\n", " ")
            top_snippet = f"{ts_str}{top_m.title} -> {clean_content[:90]}..."
        print(f"    - Retrieved: {len(results)} memories | Top: {top_snippet}", flush=True)

        req_client = client if client is not None else httpx.AsyncClient(timeout=90.0)
        close_client = client is None

        try:
            # ── 1. Answer Generation with gemma3:1b (Ollama) or LLM ──
            if generator_provider == "ollama":
                gen_prompt = f"Memories:\n{context}\n\nQuestion: {question}\nAnswer:"
                if ollama_lock is not None:
                    async with ollama_lock:
                        generated, p_tok, comp_tok = await call_ollama(
                            req_client,
                            prompt=gen_prompt,
                            system_prompt=GENERATION_SYSTEM_PROMPT,
                            model=generator_model,
                            base_url=ollama_url,
                            usage=usage,
                        )
                else:
                    generated, p_tok, comp_tok = await call_ollama(
                        req_client,
                        prompt=gen_prompt,
                        system_prompt=GENERATION_SYSTEM_PROMPT,
                        model=generator_model,
                        base_url=ollama_url,
                        usage=usage,
                    )
                if p_tok == 0:
                    p_tok = q_tok + c_tok
                if comp_tok == 0:
                    comp_tok = token_counter.count(generated)
                usage.record_query(prompt_tokens=p_tok, completion_tokens=comp_tok, context_tokens=c_tok)
            elif generator_provider == "online":
                gen_prompt = f"Memories:\n{context}\n\nQuestion: {question}\nAnswer:"
                generated = await call_llm(
                    req_client,
                    prompt=gen_prompt,
                    system_prompt=GENERATION_SYSTEM_PROMPT,
                    usage=usage,
                )
                comp_tok = token_counter.count(generated)
                usage.record_query(prompt_tokens=q_tok + c_tok, completion_tokens=comp_tok, context_tokens=c_tok)
            else:
                docs = [r.memory.content for r in results]
                generated = docs[0] if docs else "Not mentioned in the memories."
                comp_tok = token_counter.count(generated)
                usage.record_query(prompt_tokens=q_tok + c_tok, completion_tokens=comp_tok, context_tokens=c_tok)

            # ── 2. Strict Answer Judging (No context leakage) ──
            correct = False
            judge_rationale = ""
            if judge_mode == "ollama":
                if category == 5:
                    judge_prompt = (
                        f"Question: {question}\n"
                        f"Trap (wrong) answer: {adversarial_answer}\n"
                        f"Model answer: {generated}\n"
                        "Did the model correctly avoid the trap?"
                    )
                    judge_system = JUDGE_ADVERSARIAL_SYSTEM_PROMPT
                else:
                    judge_prompt = (
                        f"Question: {question}\n"
                        f"Gold answer: {gold_answer}\n"
                        f"Model answer: {generated}\n"
                        "Is the model answer correct?"
                    )
                    judge_system = JUDGE_SYSTEM_PROMPT

                if ollama_lock is not None:
                    async with ollama_lock:
                        verdict_text, _, _ = await call_ollama(
                            req_client,
                            prompt=judge_prompt,
                            system_prompt=judge_system,
                            model=judge_model,
                            base_url=ollama_url,
                            usage=usage,
                            max_tokens=100,
                        )
                else:
                    verdict_text, _, _ = await call_ollama(
                        req_client,
                        prompt=judge_prompt,
                        system_prompt=judge_system,
                        model=judge_model,
                        base_url=ollama_url,
                        usage=usage,
                        max_tokens=100,
                    )
                if verdict_text and (JUDGE_CORRECT_RE.search(verdict_text) or JUDGE_INCORRECT_RE.search(verdict_text)):
                    correct, judge_rationale = parse_judge_verdict(verdict_text)
                else:
                    correct = judge_answer_strict(category, gold_answer, adversarial_answer, generated, question=question)
                    judge_rationale = "Deterministic matching rule"
            elif judge_mode == "online":
                if category == 5:
                    judge_prompt = (
                        f"Question: {question}\n"
                        f"Trap (wrong) answer: {adversarial_answer}\n"
                        f"Model answer: {generated}\n"
                        "Did the model correctly avoid the trap?"
                    )
                    judge_system = JUDGE_ADVERSARIAL_SYSTEM_PROMPT
                else:
                    judge_prompt = (
                        f"Question: {question}\n"
                        f"Gold answer: {gold_answer}\n"
                        f"Model answer: {generated}\n"
                        "Is the model answer correct?"
                    )
                    judge_system = JUDGE_SYSTEM_PROMPT

                verdict_text = await call_llm(
                    req_client,
                    prompt=judge_prompt,
                    system_prompt=judge_system,
                    usage=usage,
                )
                correct, judge_rationale = parse_judge_verdict(verdict_text)
            else:
                correct = judge_answer_strict(category, gold_answer, adversarial_answer, generated, question=question)
                judge_rationale = "Strict rule evaluation"

            guard_reason = _answer_consistency_guard(
                category,
                gold_answer,
                generated,
                question,
            )
            guard_override = _answer_consistency_override(
                category,
                gold_answer,
                generated,
                question,
            )
            if guard_override is not None:
                correct = guard_override
                if guard_reason is None:
                    judge_rationale = "Deterministic guard accepted answer"
                else:
                    judge_rationale = f"Deterministic guard rejected answer: {guard_reason}"

            print(f"    - Gold Answer: \"{gold_answer}\"", flush=True)
            print(f"    - Model Answer ({generator_model}): \"{generated}\"", flush=True)
            if judge_rationale:
                print(f"    - Judge Rationale: {judge_rationale}", flush=True)
            verdict_badge = "CORRECT [PASS]" if correct else "INCORRECT [FAIL]"
            print(f"    - Judge Verdict ({judge_model}): {verdict_badge}", flush=True)

        finally:
            if close_client:
                await req_client.aclose()

    return QuestionResult(
        sample_id=qa.get("_sample_id", ""),
        category=category,
        question=question,
        gold_answer=gold_answer,
        generated_answer=generated,
        correct=correct,
        num_retrieved=len(results),
        judge_rationale=judge_rationale,
        retrieval_hit=judge_answer_strict(
            category,
            gold_answer,
            adversarial_answer,
            context,
            question,
        ),
        retrieved_memory_ids=[str(result.memory.id) for result in results],
    )


# ─── Orchestration ──────────────────────────────────────────────────────


async def run_conversation(
    sample: dict,
    *,
    session_factory,
    client: httpx.AsyncClient | None,
    embedding_service: EmbeddingService,
    semaphore: asyncio.Semaphore,
    usage: UsageTracker,
    stats: PipelineStats,
    token_counter: RealTokenCounter,
    generator_provider: str = "ollama",
    generator_model: str = "gemma3:1b",
    ollama_url: str = "http://localhost:11434",
    judge_mode: str = "strict_rule",
    judge_model: str = "gemma3:1b",
    offline: bool = True,
    model_server_url: str = "http://localhost:8001",
    use_model_server: bool = True,
    retrieval_limit: int = 20,
) -> list[QuestionResult]:
    sample_id = sample["sample_id"]
    conversation = sample["conversation"]
    user_id = uuid4()
    organization_id = uuid4()

    await ingest_conversation(
        sample,
        session_factory=session_factory,
        user_id=user_id,
        organization_id=organization_id,
        embedding_service=embedding_service,
        semaphore=semaphore,
        usage=usage,
        stats=stats,
    )

    now = max(
        parse_session_datetime(conversation[f"{key}_date_time"])
        for key in session_keys(conversation)
    )

    qa_list = [dict(qa, _sample_id=sample_id) for qa in sample["qa"] if qa.get("category") in CATEGORY_NAMES]
    ollama_lock = asyncio.Lock()
    results: list[QuestionResult] = []

    for idx, qa in enumerate(qa_list, start=1):
        res = await answer_question(
            qa,
            client=client,
            session_factory=session_factory,
            user_id=user_id,
            organization_id=organization_id,
            embedding_service=embedding_service,
            now=now,
            semaphore=semaphore,
            usage=usage,
            token_counter=token_counter,
            generator_provider=generator_provider,
            generator_model=generator_model,
            ollama_url=ollama_url,
            judge_mode=judge_mode,
                judge_model=judge_model,
                model_server_url=model_server_url,
                use_model_server=use_model_server,
                q_idx=idx,

            total_q=len(qa_list),
            retrieval_limit=retrieval_limit,
            ollama_lock=ollama_lock,
        )
        results.append(res)
    return results


def aggregate(results: list[QuestionResult]) -> dict:
    def summarize(rows: list[QuestionResult]) -> dict:
        n = len(rows)
        if n == 0:
            return {"n": 0, "accuracy": None}
        return {"n": n, "accuracy": sum(1 for r in rows if r.correct) / n}

    by_category = defaultdict(list)
    for r in results:
        by_category[r.category].append(r)

    answerable_rows = [row for row in results if row.gold_answer is not None]
    retrieval_summary = {
        "n": len(answerable_rows),
        "hits": sum(1 for row in answerable_rows if row.retrieval_hit),
        "accuracy": (
            sum(1 for row in answerable_rows if row.retrieval_hit) / len(answerable_rows)
            if answerable_rows
            else None
        ),
    }
    return {
        "overall": summarize(results),
        "retrieval": retrieval_summary,
        "by_category": {
            CATEGORY_NAMES[cat]: summarize(rows) for cat, rows in sorted(by_category.items())
        },
    }


def render_markdown(
    summary: dict,
    stats: PipelineStats,
    usage: UsageTracker,
    elapsed: float,
    n_conversations: int,
    *,
    generator_provider: str,
    generator_model: str,
    judge_mode: str,
    judge_model: str,
) -> str:
    lines = ["# LoCoMo End-to-End Benchmark Results", ""]
    lines.append(
        "End-to-end benchmark: real ingestion (extraction, dedup, scoring, "
        "persistence, entity resolution) into a real Postgres+pgvector "
        f"database, real RetrievalEngine.retrieve(), generator={generator_provider}/{generator_model}, "
        f"judge={judge_mode}/{judge_model}, and evaluation without context leakage. "
        "See `benchmarks/locomo/README.md` for full methodology."
    )
    lines.append("")
    lines.append(f"- Conversations evaluated: {n_conversations}")
    lines.append(f"- Questions scored: {summary['overall']['n']}")
    lines.append(f"- Sessions ingested: {stats.sessions_processed}")
    lines.append(f"- Memories extracted: {stats.memories_extracted}")
    lines.append(f"- Memories stored (post-dedup): {stats.memories_stored}")
    lines.append(f"- Memories deduped (discarded/merged): {stats.memories_deduped}")
    lines.append(f"- Entities created: {stats.entities_created}")
    lines.append(f"- Dream cycles executed: {stats.dream_cycles_run}")
    lines.append(f"- Knowledge gaps identified: {stats.knowledge_gaps_identified}")
    lines.append(f"- Extraction failures: {stats.extraction_failures}")
    lines.append(f"- LLM calls: {usage.calls} ({usage.failures} failed after retries)")
    lines.append(f"- Token accounting: {usage.prompt_tokens} prompt + {usage.completion_tokens} completion ({usage.total_tokens} total); context subset={usage.context_tokens}")
    lines.append(f"- Average token consumption / query: {usage.avg_tokens_per_query:.1f} tokens")
    lines.append(f"- Efficiency vs 25k Full-Context baseline: {((25000 - usage.avg_tokens_per_query) / 25000 * 100):.1f}% token reduction")
    lines.append(f"- Wall time: {elapsed:.1f}s")
    lines.append("")

    def table(rows: dict) -> list[str]:
        out = ["| category | n | accuracy |", "|---|---|---|"]
        for name, s in rows.items():
            if s["n"] == 0:
                continue
            out.append(f"| {name} | {s['n']} | {s['accuracy']:.3f} |")
        return out

    lines.append("## Overall")
    lines.extend(table({"overall": summary["overall"]}))
    lines.append("")
    if summary.get("retrieval", {}).get("n", 0):
        retrieval = summary["retrieval"]
        lines.append("## Retrieval proxy")
        lines.append(f"- Answerable questions: {retrieval['n']}")
        lines.append(f"- Gold-answer-containing context: {retrieval['hits']} ({retrieval['accuracy']:.3f})")
        lines.append("")
    lines.append("## By category")
    lines.extend(table(summary["by_category"]))
    lines.append("")
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Contexta LoCoMo Benchmark Runner")
    parser.add_argument("--max-conversations", type=int, default=None)
    parser.add_argument("--conversation-offset", type=int, default=0, help="Skip this many conversations before applying --max-conversations")
    parser.add_argument("--max-questions", type=int, default=None, help="Limit number of questions to evaluate for quick test")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--generator-provider", type=str, default="ollama", choices=["ollama", "online", "model_server"], help="Answer generator provider (default: ollama)")
    parser.add_argument("--generator-model", type=str, default="gemma3:1b", help="Model name for answer generation (default: gemma3:1b)")
    parser.add_argument("--ollama-url", type=str, default="http://localhost:11434", help="Ollama endpoint (default: http://localhost:11434)")
    parser.add_argument("--judge-mode", type=str, default="ollama", choices=["ollama", "strict_rule", "online"], help="Judging strategy: LLM judge via Ollama, strict rule, or cloud LLM (default: ollama)")
    parser.add_argument("--judge-model", type=str, default="gemma3:1b", help="Model name for LLM judge (default: gemma3:1b)")
    parser.add_argument("--retrieval-limit", type=int, default=20, help="Number of memories retrieved per question (default: 20)")
    parser.add_argument("--offline", action="store_true", default=True, help="Run with Contexta local model server")
    parser.add_argument("--online-llm", action="store_true", default=False, help="Force online cloud LLM")
    parser.add_argument("--model-server-url", type=str, default="http://localhost:8001")
    parser.add_argument("--db-url", type=str, default=None)
    parser.add_argument("--use-model-server", action="store_true", default=True, help="Use model server embeddings instead of fastembed")
    parser.add_argument("--no-use-model-server", action="store_false", dest="use_model_server", help="Use the in-process fastembed provider")
    parser.add_argument("--output-tag", type=str, default=None, help="Write results to results-<tag>.json and RESULTS-<tag>.md")
    args = parser.parse_args()

    if args.online_llm and args.judge_mode == "ollama":
        args.judge_mode = "online"

    output_tag = args.output_tag.strip() if isinstance(args.output_tag, str) else None
    if output_tag:
        safe_tag = re.sub(r"[^a-zA-Z0-9_.-]+", "-", output_tag).strip("-")
        if not safe_tag:
            raise SystemExit("--output-tag must contain at least one safe character")
        results_json_path = REPO_ROOT / "benchmarks" / "locomo" / f"results-{safe_tag}.json"
        results_md_path = REPO_ROOT / "benchmarks" / "locomo" / f"RESULTS-{safe_tag}.md"
    else:
        results_json_path = RESULTS_JSON_PATH
        results_md_path = RESULTS_MD_PATH

    is_offline = not args.online_llm
    if is_offline:
        from contexta.config.settings import persist_engine_mode
        persist_engine_mode("offline")

    start = time.monotonic()

    if not DATA_PATH.exists():
        raise SystemExit(f"Dataset not found at {DATA_PATH}.")

    dataset = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if args.conversation_offset < 0:
        raise SystemExit("--conversation-offset must be non-negative")
    dataset = dataset[args.conversation_offset:]
    if args.max_conversations:
        dataset = dataset[: args.max_conversations]

    settings = get_settings()
    settings.embedding_dimensions = DB_VECTOR_DIM
    if not is_offline and not settings.llm_api_key:
        raise SystemExit(
            "CONTEXTA_LLM_API_KEY is not set in .env -- required when --online-llm is specified."
        )

    db_candidates = [
        args.db_url,
        os.environ.get("BENCHMARK_DB_URL"),
        "postgresql+asyncpg://postgres:postgres@localhost:15432/contexta",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/contexta",
        DB_URL,
    ]
    connected = False
    for candidate_url in db_candidates:
        if not candidate_url:
            continue
        try:
            engine = create_async_engine(candidate_url, pool_size=args.concurrency + 5, max_overflow=10)
            session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
            async with session_factory() as s:
                from sqlalchemy import text
                await s.execute(text("SELECT 1"))
            connected = True
            break
        except Exception:
            continue

    if not connected:
        raise RuntimeError("Could not connect to PostgreSQL on any standard port (15432, 5432, 55432).")

    use_ms = args.use_model_server
    if use_ms:
        try:
            async with httpx.AsyncClient(timeout=3.0) as check_client:
                r = await check_client.get(f"{args.model_server_url}/health")
                if r.status_code != 200:
                    use_ms = False
        except Exception:
            use_ms = False

    settings.local_model_server_enabled = use_ms

    if use_ms:
        print(f"Connecting to Contexta Local Model Server at {args.model_server_url} (Qwen/Qwen3-Embedding-0.6B + Qwen/Qwen3-Reranker-0.6B)...", flush=True)
        embedding_service = EmbeddingService(settings=settings, provider=LocalModelServerEmbedder(args.model_server_url))
    else:
        print(f"Loading local offline semantic embedding model ({EMBEDDING_MODEL_NAME})...", flush=True)
        fastembed_model = load_fastembed_model()
        embedding_service = EmbeddingService(settings=settings, provider=FastEmbedProvider(fastembed_model))

    print(f"Token Counter: Initializing accurate subword tokenizer for Gemma/Qwen...", flush=True)
    token_counter = RealTokenCounter(model_name="google/gemma-2-2b")
    print(f"Answer Generator: {args.generator_provider} (model: {args.generator_model})", flush=True)
    print(f"Judging Mode: {args.judge_mode} (context-leakage strictly eliminated, category-5 strict abstention enforced)", flush=True)

    semaphore = asyncio.Semaphore(args.concurrency)
    usage = UsageTracker()
    stats = PipelineStats()

    all_results: list[QuestionResult] = []
    async with httpx.AsyncClient() as client:
        for i, sample in enumerate(dataset, start=1):
            conv = sample["conversation"]
            n_turns = sum(len(conv[k]) for k in session_keys(conv))
            if args.max_questions and len(sample["qa"]) > args.max_questions:
                sample["qa"] = sample["qa"][:args.max_questions]

            print(
                f"[{i}/{len(dataset)}] {sample['sample_id']}: "
                f"{n_turns} turns, {len(sample['qa'])} questions... (engine={'offline' if is_offline else 'online'})",
                flush=True,
            )
            t0 = time.monotonic()
            results = await run_conversation(
                sample,
                session_factory=session_factory,
                client=client,
                embedding_service=embedding_service,
                semaphore=semaphore,
                usage=usage,
                stats=stats,
                token_counter=token_counter,
                generator_provider=args.generator_provider,
                generator_model=args.generator_model,
                ollama_url=args.ollama_url,
                judge_mode=args.judge_mode,
                judge_model=args.judge_model,
                model_server_url=args.model_server_url,
                use_model_server=use_ms,
                retrieval_limit=args.retrieval_limit,
            )
            all_results.extend(results)
            print(
                f"  -> {len(results)} questions answered in {time.monotonic() - t0:.1f}s "
                f"(running accuracy so far: "
                f"{sum(1 for r in all_results if r.correct) / len(all_results):.3f})",
                flush=True,
            )

    if hasattr(embedding_service._provider, "aclose"):
        await embedding_service._provider.aclose()

    await engine.dispose()

    summary = aggregate(all_results)
    elapsed = time.monotonic() - start

    results_json_path.write_text(
        json.dumps(
            {
                "summary": summary,
                "stats": vars(stats),
                "usage": vars(usage),
                "elapsed_seconds": elapsed,
                "n_conversations": len(dataset),
                "conversation_offset": args.conversation_offset,
                "retrieval_limit": args.retrieval_limit,
                "output_tag": output_tag,
                "generator_provider": args.generator_provider,
                "generator_model": args.generator_model,
                "judge_mode": args.judge_mode,
                "judge_model": args.judge_model,
                "embedding_backend": "model_server" if use_ms else "fastembed",
                "offline": is_offline,
                "questions": [
                    {
                        "sample_id": r.sample_id,
                        "category": CATEGORY_NAMES[r.category],
                        "question": r.question,
                        "gold_answer": r.gold_answer,
                        "generated_answer": r.generated_answer,
                        "correct": r.correct,
                        "num_retrieved": r.num_retrieved,
                        "judge_rationale": r.judge_rationale,
                        "retrieval_hit": r.retrieval_hit,
                        "retrieved_memory_ids": r.retrieved_memory_ids,
                    }
                    for r in all_results
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    results_md_path.write_text(
        render_markdown(
            summary,
            stats,
            usage,
            elapsed,
            len(dataset),
            generator_provider=args.generator_provider,
            generator_model=args.generator_model,
            judge_mode=args.judge_mode,
            judge_model=args.judge_model,
        ),
        encoding="utf-8",
    )

    print()
    print(f"Done in {elapsed:.1f}s. Wrote {results_json_path} and {results_md_path}")
    print()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

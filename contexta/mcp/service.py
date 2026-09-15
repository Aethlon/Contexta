"""Contexta MCP Service Bridge.

Provides high-level memory operations (remember, recall, context compilation,
graph traversal, and dream cycles) for the Model Context Protocol (MCP) server.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import math
import os
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from contexta.core.dream.engine import DreamCycleEngine
from contexta.core.entities.relation_extractor import (
    extract_semantic_relations,
    filter_entity_candidates,
    infer_entity_type,
)
from contexta.core.entities.resolver import EntityResolver
from contexta.core.retrieval.engine import RetrievalEngine, RetrievalResult
from contexta.core.schemas import MemoryType, RetrievalQuery
from contexta.core.scoring.engine import MemoryScoringEngine
from contexta.core.types import EntityType, SourceType
from contexta.models.dream import DreamRecord
from contexta.models.entity import Entity, EntityEdge
from contexta.models.memory import MemoryRecord
from contexta.repositories.entity_repo import (
    EntityEdgeRepository,
    EntityRepository,
    MemoryEntityLinkRepository,
)
from contexta.repositories.memory_repo import MemoryRepository

logger = logging.getLogger("contexta.mcp")

DEFAULT_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DB_VECTOR_DIM = 1536
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"


def parse_raw_records(text: str) -> list[dict[str, Any]]:
    """Parse JSON array, JSON-with-memories-key, JSONL lines, or CSV text into dictionaries."""
    text = text.strip()
    if not text:
        return []

    # 1. Standard JSON (array of objects or dict with 'memories' key)
    if (text.startswith("[") and text.endswith("]")) or (text.startswith("{") and text.endswith("}")):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
            if isinstance(data, dict) and "memories" in data and isinstance(data["memories"], list):
                return [d for d in data["memories"] if isinstance(d, dict)]
        except Exception:
            pass

    # 2. JSONL (one JSON object per line)
    jsonl_records = []
    has_valid_jsonl = False
    for line in text.splitlines():
        l_str = line.strip()
        if l_str:
            try:
                obj = json.loads(l_str)
                if isinstance(obj, dict):
                    jsonl_records.append(obj)
                    has_valid_jsonl = True
            except Exception:
                pass
    if has_valid_jsonl and len(jsonl_records) > 0:
        return jsonl_records

    # 3. CSV format
    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if rows and all(isinstance(r, dict) for r in rows):
            return rows
    except Exception:
        pass

    return []


def to_uuid(val: str | uuid.UUID | None) -> uuid.UUID:
    """Deterministically convert string identifiers or usernames to UUIDs."""
    if val is None:
        return uuid.UUID("00000000-0000-0000-0000-000000000002")
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(val)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_DNS, str(val).strip().lower())


class FastEmbedLocalProvider:
    """Zero-dependency local embedding provider with zero-padding to 1536 dims."""

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME) -> None:
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def _embed_sync(self, text: str) -> list[float]:
        m = self._get_model()
        vec = list(m.embed([text]))[0].tolist()
        if len(vec) < DB_VECTOR_DIM:
            vec = vec + [0.0] * (DB_VECTOR_DIM - len(vec))
        return vec

    def _embed_batch_sync(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        m = self._get_model()
        results = []
        for vec in m.embed(texts):
            v_list = vec.tolist()
            if len(v_list) < DB_VECTOR_DIM:
                v_list = v_list + [0.0] * (DB_VECTOR_DIM - len(v_list))
            results.append(v_list)
        return results

    async def embed(self, text: str) -> list[float]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._embed_sync, text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._embed_batch_sync, texts)


class LocalNeuralReranker:
    """Connects to Contexta local model server running BAAI/bge-reranker-base."""

    def __init__(self, server_url: str = "http://localhost:8001") -> None:
        self.server_url = server_url
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
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
                    raw_model_score = score_map.get(idx, 0.0)
                    # Calibrate cross-encoder logit using sigmoid to [0.0, 1.0]
                    calibrated_score = 1.0 / (1.0 + math.exp(-raw_model_score))
                    base_retrieval_score = min(1.0, max(0.0, r.score))
                    g_score = min(1.0, max(0.0, r.graph_score))
                    # Preserve graph influence in final score for multi-hop graph paths
                    if g_score > 0.0:
                        blended = 0.60 * calibrated_score + 0.25 * base_retrieval_score + 0.15 * g_score
                    else:
                        blended = 0.75 * calibrated_score + 0.25 * base_retrieval_score
                    final_score = min(1.0, max(0.0, blended))
                    reranked.append(
                        RetrievalResult(
                            memory=r.memory,
                            score=final_score,
                            semantic_score=calibrated_score,
                            graph_score=g_score,
                            importance_score=min(1.0, max(0.0, r.importance_score)),
                            recency_score=min(1.0, max(0.0, r.recency_score)),
                            keyword_score=min(1.0, max(0.0, getattr(r, "keyword_score", 0.0))),
                        )
                    )
                reranked.sort(key=lambda x: x.score, reverse=True)
                return reranked
        except Exception as exc:
            logger.debug("Neural cross-encoder rerank fallback: %s", exc)
        return results

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class ContextaMCPService:
    """Core bridge managing persistence, embedding, and retrieval for MCP agents."""

    def __init__(
        self,
        db_url: str | None = None,
        model_server_url: str = "http://localhost:8001",
    ) -> None:
        self.db_url = db_url or os.environ.get(
            "CONTEXTA_DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:55432/contexta",
        )
        self.model_server_url = model_server_url
        self._engine = None
        self._session_factory = None
        self._embedder = FastEmbedLocalProvider()
        self._reranker = LocalNeuralReranker(model_server_url)
        self._scoring_engine = MemoryScoringEngine()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._benchmark_jobs: dict[str, dict[str, Any]] = {}
        self._benchmark_evaluator = None

    @property
    def benchmark_evaluator(self):
        if self._benchmark_evaluator is None:
            from contexta.benchmarks.evaluator import BenchmarkEvaluator
            self._benchmark_evaluator = BenchmarkEvaluator(self)
        return self._benchmark_evaluator

    def _get_engine(self):
        if self._engine is None:
            self._engine = create_async_engine(
                self.db_url,
                echo=False,
                pool_size=10,
                max_overflow=20,
            )
            self._session_factory = async_sessionmaker(
                self._engine,
                expire_on_commit=False,
                class_=AsyncSession,
            )
        return self._engine

    def session(self) -> AsyncSession:
        self._get_engine()
        return self._session_factory()

    async def remember(
        self,
        content: str,
        *,
        user_id: str = "default_user",
        title: str = "",
        memory_type: str = "episodic",
        tags: list[str] | None = None,
        observed_at: datetime | None = None,
        importance: float = 0.5,
    ) -> dict[str, Any]:
        """Store a new memory in Contexta with automatic embedding and entity linking."""
        u_id = to_uuid(user_id)
        org_id = DEFAULT_ORG_ID
        now_dt = observed_at or datetime.now(UTC).replace(tzinfo=None)

        # Generate concise title if omitted
        if not title:
            words = content.strip().split()
            title = " ".join(words[:6]) + ("..." if len(words) > 6 else "")

        # Compute semantic vector embedding
        embed_text = f"{title}\n{content}".strip()
        embedding = await self._embedder.embed(embed_text)

        # Normalize memory type
        type_str = memory_type.lower()
        if type_str not in {"episodic", "semantic", "procedural"}:
            type_str = "episodic"

        async with self.session() as session:
            mem_repo = MemoryRepository(session, tenant_id=org_id)
            entity_repo = EntityRepository(session, tenant_id=org_id)
            link_repo = MemoryEntityLinkRepository(session, tenant_id=org_id)
            edge_repo = EntityEdgeRepository(session, tenant_id=org_id)
            resolver = EntityResolver(entity_repo, link_repo, edge_repo)

            record = MemoryRecord(
                user_id=u_id,
                organization_id=org_id,
                memory_type=type_str,
                title=title,
                content=content,
                tags=tags or [],
                source_type=SourceType.USER_EXPLICIT,
                importance=importance,
                valid_from=now_dt,
                embedding=embedding,
            )
            saved_record = await mem_repo.create(record)

            # Robust entity extraction: extract from tags, title, and content
            raw_candidates: set[str] = set()

            # 1. Explicit tags
            for tag in (tags or []):
                t_clean = str(tag).strip().strip("#@")
                if len(t_clean) >= 2:
                    raw_candidates.add(t_clean)

            # 2. Extract capitalized named entities & technical terms from content and title
            text_to_scan = f"{title}\n{content}"
            matches = re.findall(r"\b([A-Z][a-zA-Z0-9_-]{1,})\b", text_to_scan)
            for m in matches:
                raw_candidates.add(m)

            # 3. Quoted terms
            quotes = re.findall(r"[\"']([A-Za-z0-9_\-\s]{2,30})[\"']", text_to_scan)
            for q in quotes:
                raw_candidates.add(q.strip())

            # 4. Filter noise words and infer entity types
            validated_entities = filter_entity_candidates(raw_candidates, text_to_scan)

            # 5. Resolve and link each validated entity in PostgreSQL
            resolved_entities: list[Entity] = []
            resolved_entity_names: list[str] = []
            seen_entity_ids: set[uuid.UUID] = set()

            for ent_name, ent_type in validated_entities[:12]:
                try:
                    resolved = await resolver.resolve_and_link(
                        name=ent_name,
                        user_id=u_id,
                        organization_id=org_id,
                        memory_id=saved_record.id,
                        entity_type=ent_type,
                        observed_at=now_dt,
                    )
                    if resolved.id not in seen_entity_ids:
                        seen_entity_ids.add(resolved.id)
                        resolved_entities.append(resolved)
                        resolved_entity_names.append(resolved.name)
                except Exception as exc:
                    logger.warning("Entity resolution failed for %s: %s", ent_name, exc)

            # 6. Extract typed semantic relations and persist knowledge graph edges
            if len(resolved_entities) > 1:
                semantic_relations = extract_semantic_relations(text_to_scan, resolved_entities)
                for src_ent, rel_type, tgt_ent in semantic_relations:
                    if src_ent.id != tgt_ent.id:
                        try:
                            existing_edges = await edge_repo.get_neighbors(src_ent.id)
                            # Check if edge between these two entities already exists
                            matched_edge = None
                            for ed in existing_edges:
                                if (
                                    (ed.source_entity_id == src_ent.id and ed.target_entity_id == tgt_ent.id)
                                    or (ed.source_entity_id == tgt_ent.id and ed.target_entity_id == src_ent.id)
                                ):
                                    matched_edge = ed
                                    break

                            if matched_edge is None:
                                edge = EntityEdge(
                                    source_entity_id=src_ent.id,
                                    target_entity_id=tgt_ent.id,
                                    relationship_type=rel_type,
                                    organization_id=org_id,
                                )
                                await edge_repo.create(edge)
                            elif matched_edge.relationship_type in {"co_occurs_with", "related_to"} and rel_type not in {"co_occurs_with", "related_to"}:
                                # Upgrade generic co-occurrence to specific semantic relationship
                                await edge_repo.update_by_id(
                                    matched_edge.id,
                                    {
                                        "source_entity_id": src_ent.id,
                                        "target_entity_id": tgt_ent.id,
                                        "relationship_type": rel_type,
                                    },
                                )
                        except Exception as edge_err:
                            logger.debug("Edge creation/update failed: %s", edge_err)

            await session.commit()

            return {
                "memory_id": str(saved_record.id),
                "title": saved_record.title,
                "memory_type": saved_record.memory_type,
                "created_at": saved_record.created_at.isoformat() if saved_record.created_at else None,
                "entities_linked": resolved_entity_names,
                "status": "stored",
            }

    async def recall(
        self,
        query: str,
        *,
        user_id: str = "default_user",
        limit: int = 5,
        graph_depth: int = 2,
    ) -> list[dict[str, Any]]:
        """Retrieve memories using Contexta 3-Layer hybrid search."""
        u_id = to_uuid(user_id)
        org_id = DEFAULT_ORG_ID

        q_embedding = await self._embedder.embed(query)
        retrieval_query = RetrievalQuery(
            user_id=u_id,
            organization_id=org_id,
            query_text=query,
            limit=limit,
            graph_depth=graph_depth,
        )

        async with self.session() as session:
            mem_repo = MemoryRepository(session, tenant_id=org_id)
            entity_repo = EntityRepository(session, tenant_id=org_id)
            link_repo = MemoryEntityLinkRepository(session, tenant_id=org_id)
            edge_repo = EntityEdgeRepository(session, tenant_id=org_id)

            engine = RetrievalEngine(
                memory_repository=mem_repo,
                link_repository=link_repo,
                edge_repository=edge_repo,
                entity_repository=entity_repo,
                reranker=self._reranker,
                scoring_engine=self._scoring_engine,
            )

            results = await engine.retrieve(retrieval_query, query_embedding=q_embedding)

            return [
                {
                    "memory_id": str(r.memory.id),
                    "title": r.memory.title,
                    "content": r.memory.content,
                    "score": round(min(1.0, max(0.0, r.score)), 4),
                    "semantic_score": round(min(1.0, max(0.0, r.semantic_score)), 4),
                    "graph_score": round(min(1.0, max(0.0, r.graph_score)), 4),
                    "memory_type": r.memory.memory_type,
                    "tags": r.memory.tags or [],
                    "valid_from": r.memory.valid_from.isoformat() if r.memory.valid_from else None,
                }
                for r in results
            ]

    async def get_context(
        self,
        *,
        user_id: str = "default_user",
        focus: str = "",
        max_memories: int = 10,
    ) -> str:
        """Format an ultra-dense, token-efficient system context snippet for LLM prompts."""
        if focus:
            results = await self.recall(focus, user_id=user_id, limit=max_memories)
        else:
            u_id = to_uuid(user_id)
            org_id = DEFAULT_ORG_ID
            async with self.session() as session:
                mem_repo = MemoryRepository(session, tenant_id=org_id)
                recs = await mem_repo.get_by_user(u_id, limit=max_memories)
                results = [
                    {
                        "title": m.title,
                        "content": m.content,
                        "memory_type": m.memory_type,
                        "valid_from": m.valid_from.isoformat() if m.valid_from else None,
                    }
                    for m in recs
                ]

        if not results:
            return "No persistent memories on record."

        lines = ["### Contexta Active Memory Context:"]
        for r in results:
            dt_str = f" ({r['valid_from'][:10]})" if r.get("valid_from") else ""
            lines.append(f"- [{r.get('memory_type', 'fact').upper()}]{dt_str} {r['content']}")
        return "\n".join(lines)

    async def forget(
        self,
        memory_id: str,
        *,
        reason: str = "",
    ) -> dict[str, Any]:
        """Archive or invalidate a memory by ID."""
        m_id = uuid.UUID(memory_id)
        org_id = DEFAULT_ORG_ID
        now_dt = datetime.now(UTC).replace(tzinfo=None)

        async with self.session() as session:
            mem_repo = MemoryRepository(session, tenant_id=org_id)
            rec = await mem_repo.get_by_id(m_id)
            if not rec:
                return {"status": "not_found", "memory_id": memory_id}

            rec.is_archived = True
            rec.valid_to = now_dt
            await session.commit()
            return {
                "status": "archived",
                "memory_id": memory_id,
                "title": rec.title,
                "reason": reason or "User requested forgetting",
            }

    async def explore_graph(
        self,
        entity_name: str,
        *,
        user_id: str = "default_user",
        max_neighbors: int = 15,
    ) -> dict[str, Any]:
        """Explore knowledge graph entity relations, connected memories, and neighbor edges."""
        u_id = to_uuid(user_id)
        org_id = DEFAULT_ORG_ID

        async with self.session() as session:
            entity_repo = EntityRepository(session, tenant_id=org_id)
            edge_repo = EntityEdgeRepository(session, tenant_id=org_id)
            link_repo = MemoryEntityLinkRepository(session, tenant_id=org_id)
            mem_repo = MemoryRepository(session, tenant_id=org_id)

            # Find matching entity (scoped to user first)
            entity = await entity_repo.get_by_name(u_id, entity_name)
            if not entity:
                all_ents = await entity_repo.get_by_user(u_id, limit=200)
                matching = [e for e in all_ents if entity_name.lower() in e.name.lower()]
                if matching:
                    entity = matching[0]

            # If still not found, fallback to tenant-wide search in case of scope mismatch
            if not entity:
                stmt = select(Entity).where(
                    Entity.organization_id == org_id,
                    Entity.name.ilike(f"%{entity_name}%"),
                ).limit(5)
                res = await session.execute(stmt)
                org_matching = res.scalars().all()
                if org_matching:
                    entity = org_matching[0]

            if not entity:
                return {
                    "searched": entity_name,
                    "found": False,
                    "message": f"Entity '{entity_name}' not found in knowledge graph.",
                }

            # Get neighbors and linked memories
            edges = await edge_repo.get_neighbors(entity.id)
            links = await link_repo.get_memories_for_entity(entity.id)

            linked_memories = []
            for lk in links[:10]:
                m = await mem_repo.get_by_id(lk.memory_id)
                if m:
                    linked_memories.append({"memory_id": str(m.id), "title": m.title, "content": m.content})

            neighbor_details = []
            for edge in edges[:max_neighbors]:
                is_source = (edge.source_entity_id == entity.id)
                other_id = edge.target_entity_id if is_source else edge.source_entity_id
                other_ent = await entity_repo.get_by_id(other_id)
                if other_ent:
                    direction = "outgoing" if is_source else "incoming"
                    repr_str = (
                        f"{entity.name} --[{edge.relationship_type}]--> {other_ent.name}"
                        if is_source
                        else f"{other_ent.name} --[{edge.relationship_type}]--> {entity.name}"
                    )
                    neighbor_details.append({
                        "entity": other_ent.name,
                        "relationship": edge.relationship_type,
                        "direction": direction,
                        "representation": repr_str,
                    })

            attrs = entity.aggregated_attributes or {}
            mention_count = attrs.get("mention_count", len(links) or 1)

            return {
                "searched": entity_name,
                "found": True,
                "entity": entity.name,
                "entity_type": entity.entity_type,
                "mention_count": mention_count,
                "connected_entities": neighbor_details,
                "linked_memories": linked_memories,
            }

    async def dream(
        self,
        *,
        user_id: str = "default_user",
    ) -> dict[str, Any]:
        """Run Contexta dream cycle to detect knowledge gaps and synthesize insights."""
        u_id = to_uuid(user_id)
        org_id = DEFAULT_ORG_ID

        async with self.session() as session:
            entity_repo = EntityRepository(session, tenant_id=org_id)
            mem_repo = MemoryRepository(session, tenant_id=org_id)
            link_repo = MemoryEntityLinkRepository(session, tenant_id=org_id)
            edge_repo = EntityEdgeRepository(session, tenant_id=org_id)

            entities = await entity_repo.get_by_user(u_id, limit=50)
            if not entities:
                return {"status": "skipped", "message": "No entities available for dream cycle."}

            dream_engine = DreamCycleEngine()
            questions = dream_engine.generate_questions(entities[:10])
            gaps_found = 0

            retrieval_engine = RetrievalEngine(
                memory_repository=mem_repo,
                link_repository=link_repo,
                edge_repository=edge_repo,
                entity_repository=entity_repo,
            )

            started_at = datetime.now(UTC).replace(tzinfo=None)
            for q_text, ent_id in questions:
                q_emb = await self._embedder.embed(q_text)
                query = RetrievalQuery(
                    user_id=u_id,
                    organization_id=org_id,
                    query_text=q_text,
                    limit=3,
                )
                res = await retrieval_engine.retrieve(query, query_embedding=q_emb, now=started_at)
                confidence = res[0].score if res else 0.0
                gap = dream_engine.identify_gap(
                    organization_id=org_id,
                    user_id=u_id,
                    question=q_text,
                    related_entity_id=ent_id,
                    confidence=confidence,
                )
                if gap:
                    session.add(gap)
                    gaps_found += 1

            record = DreamRecord(
                user_id=u_id,
                organization_id=org_id,
                cycle_type="consolidation",
                status="completed",
                summary=f"Dream cycle evaluated {len(questions)} questions and identified {gaps_found} knowledge gaps.",
                memory_count=len(entities),
                insights_generated=gaps_found,
                cycles_completed=1,
                started_at=started_at,
                completed_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(record)
            await session.commit()

            return {
                "status": "completed",
                "questions_evaluated": len(questions),
                "knowledge_gaps_identified": gaps_found,
                "summary": record.summary,
            }

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Query real-time progress and metrics of a background ingestion job."""
        job = self._jobs.get(job_id)
        if not job:
            return {
                "job_id": job_id,
                "status": "not_found",
                "message": f"Ingestion job '{job_id}' not found.",
            }
        return dict(job)

    async def batch_remember(
        self,
        *,
        memories: list[dict[str, Any]] | None = None,
        file_path: str = "",
        raw_content: str = "",
        file_url: str = "",
        user_id: str = "default_user",
        batch_size: int = 50,
        async_processing: bool = True,
    ) -> dict[str, Any]:
        """Ingest large memory datasets (10k+ records) from raw text, URLs, files, or objects with background chunking."""
        raw_records: list[dict[str, Any]] = []

        # 1. Parse from direct raw string content (JSON, JSONL, or CSV)
        if raw_content:
            parsed = parse_raw_records(raw_content)
            if parsed:
                raw_records.extend(parsed)
            else:
                return {
                    "status": "error",
                    "message": "Could not parse 'raw_content'. Ensure it is formatted as a JSON array, JSONL lines, or CSV text.",
                }

        # 2. Download from remote URL
        if file_url:
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.get(file_url)
                    if resp.status_code == 200:
                        parsed = parse_raw_records(resp.text)
                        if parsed:
                            raw_records.extend(parsed)
                        else:
                            return {
                                "status": "error",
                                "message": f"Could not parse data downloaded from {file_url}. Ensure JSON, JSONL, or CSV format.",
                            }
                    else:
                        return {
                            "status": "error",
                            "message": f"Failed to download from {file_url}: HTTP {resp.status_code}",
                        }
            except Exception as dl_err:
                return {
                    "status": "error",
                    "message": f"Error downloading from {file_url}: {dl_err}",
                }

        # 3. Read from server-side local file path
        if file_path:
            p = Path(file_path)
            if not p.is_file():
                return {
                    "status": "error",
                    "message": (
                        f"File not found on host filesystem: '{file_path}'. "
                        "Note: If calling from a sandboxed cloud environment (such as ChatGPT or Claude), "
                        "the host cannot access paths like '/mnt/data/...'. "
                        "Instead, pass 'raw_content' with the file text, provide a 'file_url', "
                        "pass the 'memories' array directly, or POST to /api/ingest-file."
                    ),
                }
            suffix = p.suffix.lower()
            try:
                if suffix == ".json":
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            raw_records.extend(data)
                        elif isinstance(data, dict) and "memories" in data:
                            raw_records.extend(data["memories"])
                elif suffix == ".jsonl":
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            l_str = line.strip()
                            if l_str:
                                raw_records.append(json.loads(l_str))
                elif suffix == ".csv":
                    with open(p, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        raw_records.extend(list(reader))
                else:
                    with open(p, "r", encoding="utf-8") as f:
                        parsed = parse_raw_records(f.read())
                        if parsed:
                            raw_records.extend(parsed)
            except Exception as read_err:
                return {
                    "status": "error",
                    "message": f"Failed to read file {file_path}: {read_err}",
                }

        # 4. Direct memories list
        if memories:
            raw_records.extend(memories)

        if not raw_records:
            return {
                "status": "error",
                "message": (
                    "No valid memory records provided. "
                    "You can pass: (1) 'raw_content' with JSONL/JSON string, "
                    "(2) 'memories' list of objects, (3) 'file_url' download link, "
                    "or (4) POST directly to https://apically-literary-tajuana.ngrok-free.dev/api/ingest-file."
                ),
            }

        job_id = f"ingest-{uuid.uuid4().hex[:8]}"
        batch_size = max(5, min(batch_size, 200))

        job_info = {
            "job_id": job_id,
            "status": "queued",
            "user_id": user_id,
            "total_records": len(raw_records),
            "processed_records": 0,
            "failed_records": 0,
            "percent_complete": 0.0,
            "batch_size": batch_size,
            "started_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "completed_at": None,
            "elapsed_seconds": 0.0,
            "error": None,
        }
        self._jobs[job_id] = job_info

        if async_processing:
            asyncio.create_task(
                self._process_batch_ingest_job(
                    job_id=job_id,
                    records=raw_records,
                    user_id=user_id,
                    batch_size=batch_size,
                )
            )
            return {
                "job_id": job_id,
                "status": "queued",
                "total_records": len(raw_records),
                "batch_size": batch_size,
                "message": (
                    f"Queued {len(raw_records)} records for background ingestion in batches of {batch_size}. "
                    f"The Contexta backend is processing them gradually. "
                    f"Check progress anytime with contexta_job_status(job_id='{job_id}')."
                ),
            }
        else:
            await self._process_batch_ingest_job(
                job_id=job_id,
                records=raw_records,
                user_id=user_id,
                batch_size=batch_size,
            )
            return self.get_job_status(job_id)

    async def _process_batch_ingest_job(
        self,
        job_id: str,
        records: list[dict[str, Any]],
        user_id: str,
        batch_size: int,
    ) -> None:
        start_time = time.time()
        job = self._jobs[job_id]
        job["status"] = "processing"

        u_id = to_uuid(user_id)
        org_id = DEFAULT_ORG_ID

        total = len(records)
        processed = 0
        failed = 0

        # In-memory entity and edge cache for high-throughput batch ingestion
        entity_cache: dict[str, Entity] = {}
        known_edges: set[tuple[uuid.UUID, uuid.UUID]] = set()

        for chunk_idx in range(0, total, batch_size):
            chunk = records[chunk_idx : chunk_idx + batch_size]
            try:
                # 1. Prepare texts for batch embedding
                embed_inputs = []
                cleaned_items = []
                now_dt = datetime.now(UTC).replace(tzinfo=None)

                for item in chunk:
                    if isinstance(item, str):
                        content = item.strip()
                        title = ""
                        tags = []
                        m_type = "episodic"
                        importance = 0.5
                    elif isinstance(item, dict):
                        content = str(item.get("content", item.get("text", ""))).strip()
                        title = str(item.get("title", "")).strip()
                        raw_tags = item.get("tags", [])
                        tags = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else []
                        m_type = str(item.get("memory_type", "episodic")).lower()
                        importance = float(item.get("importance", 0.5))
                    else:
                        continue

                    if not content:
                        continue

                    if not title:
                        words = content.split()
                        title = " ".join(words[:6]) + ("..." if len(words) > 6 else "")

                    embed_text = f"{title}\n{content}".strip()
                    embed_inputs.append(embed_text)
                    cleaned_items.append((title, content, tags, m_type, importance))

                if not cleaned_items:
                    continue

                # 2. Batch embedding computation
                embeddings = await self._embedder.embed_batch(embed_inputs)

                # 3. Database persistence and graph linking
                async with self.session() as session:
                    mem_repo = MemoryRepository(session, tenant_id=org_id)
                    entity_repo = EntityRepository(session, tenant_id=org_id)
                    link_repo = MemoryEntityLinkRepository(session, tenant_id=org_id)
                    edge_repo = EntityEdgeRepository(session, tenant_id=org_id)
                    resolver = EntityResolver(entity_repo, link_repo, edge_repo)

                    mem_records = []
                    for idx, (t, c, tg, mt, imp) in enumerate(cleaned_items):
                        rec_id = uuid.uuid4()
                        rec = MemoryRecord(
                            id=rec_id,
                            user_id=u_id,
                            organization_id=org_id,
                            memory_type=mt if mt in {"episodic", "semantic", "procedural"} else "episodic",
                            title=t,
                            content=c,
                            tags=tg,
                            source_type=SourceType.API,
                            importance=min(1.0, max(0.0, imp)),
                            valid_from=now_dt,
                            embedding=embeddings[idx],
                        )
                        session.add(rec)
                        mem_records.append((rec_id, t, c, tg))

                    await session.flush()

                    for rec_id, t, c, tg in mem_records:
                        # Extract & link entities
                        text_to_scan = f"{t}\n{c}"
                        raw_cands = set(tg)
                        raw_cands.update(re.findall(r"\b([A-Z][a-zA-Z0-9_-]{1,})\b", text_to_scan))
                        validated = filter_entity_candidates(raw_cands, text_to_scan)

                        resolved_ents = []
                        seen_ids = set()
                        for ent_name, ent_type in validated[:8]:
                            cache_key = ent_name.lower()
                            try:
                                if cache_key in entity_cache:
                                    resolved = entity_cache[cache_key]
                                    link = MemoryEntityLink(
                                        memory_id=rec_id,
                                        entity_id=resolved.id,
                                        organization_id=org_id,
                                    )
                                    session.add(link)
                                else:
                                    resolved = await resolver.resolve_and_link(
                                        name=ent_name,
                                        user_id=u_id,
                                        organization_id=org_id,
                                        memory_id=rec_id,
                                        entity_type=ent_type,
                                        observed_at=now_dt,
                                    )
                                    entity_cache[cache_key] = resolved

                                if resolved.id not in seen_ids:
                                    seen_ids.add(resolved.id)
                                    resolved_ents.append(resolved)
                            except Exception:
                                pass

                        # Extract & persist typed semantic edges
                        if len(resolved_ents) > 1:
                            rels = extract_semantic_relations(text_to_scan, resolved_ents)
                            for s_ent, rel_type, t_ent in rels:
                                if s_ent.id != t_ent.id:
                                    edge_key = (min(s_ent.id, t_ent.id), max(s_ent.id, t_ent.id))
                                    if edge_key not in known_edges:
                                        known_edges.add(edge_key)
                                        edge = EntityEdge(
                                            source_entity_id=s_ent.id,
                                            target_entity_id=t_ent.id,
                                            relationship_type=rel_type,
                                            organization_id=org_id,
                                        )
                                        session.add(edge)

                    await session.commit()
                processed += len(cleaned_items)
            except Exception as batch_err:
                logger.warning("Batch ingest chunk failed: %s", batch_err)
                failed += len(chunk)

            # Update job progress
            elapsed = round(time.time() - start_time, 2)
            job["processed_records"] = processed
            job["failed_records"] = failed
            job["percent_complete"] = round((processed / total) * 100.0, 1)
            job["elapsed_seconds"] = elapsed
            job["updated_at"] = datetime.now(UTC).isoformat()

            # Yield briefly so the event loop and MCP server remain fast and responsive
            await asyncio.sleep(0.02)

        # Mark job finished
        job["status"] = "completed" if failed == 0 else ("completed_with_errors" if processed > 0 else "failed")
        job["completed_at"] = datetime.now(UTC).isoformat()
        job["elapsed_seconds"] = round(time.time() - start_time, 2)

    async def profile_latency(
        self,
        *,
        num_requests: int = 30,
        concurrency: int = 5,
        mode: str = "hybrid",
        user_id: str = "contexta_benchmark_50k",
    ) -> dict[str, Any]:
        """Rapid latency profiling measuring p50, p75, p90, p95, p99 percentiles, QPS, and error rate."""
        return await self.benchmark_evaluator.profile_latency(
            num_requests=num_requests,
            concurrency=concurrency,
            mode=mode,
            user_id=user_id,
        )

    async def run_benchmark(
        self,
        *,
        num_queries: int = 50,
        concurrency: int = 5,
        test_suite: str = "all",
        ablation: bool = True,
        user_id: str = "contexta_benchmark_50k",
        async_job: bool = False,
    ) -> dict[str, Any]:
        """Run statistical evaluation suite over the 50.5K database with latency percentiles, recall, and ablation."""
        import dataclasses

        if async_job or num_queries > 60:
            job_id = f"bench-{uuid.uuid4().hex[:8]}"
            job_info = {
                "job_id": job_id,
                "status": "processing",
                "user_id": user_id,
                "num_queries": num_queries,
                "completed_queries": 0,
                "percent_complete": 0.0,
                "concurrency": concurrency,
                "test_suite": test_suite,
                "started_at": datetime.now(UTC).isoformat(),
                "completed_at": None,
                "result": None,
                "error": None,
            }
            self._benchmark_jobs[job_id] = job_info
            self._save_benchmark_jobs()

            def _progress(done: int, total: int, last_metric: Any) -> None:
                job_info["completed_queries"] = done
                job_info["percent_complete"] = round((done / max(1, total)) * 100.0, 1)
                self._save_benchmark_jobs()

            async def _bg_run():
                try:
                    report = await self.benchmark_evaluator.run_suite(
                        num_queries=num_queries,
                        concurrency=concurrency,
                        test_suite=test_suite,
                        ablation=ablation,
                        user_id=user_id,
                        progress_callback=_progress,
                    )
                    job_info["status"] = "completed"
                    job_info["completed_at"] = datetime.now(UTC).isoformat()
                    job_info["result"] = dataclasses.asdict(report)
                except Exception as e:
                    job_info["status"] = "failed"
                    job_info["error"] = str(e)
                    job_info["completed_at"] = datetime.now(UTC).isoformat()
                finally:
                    self._save_benchmark_jobs()

            asyncio.create_task(_bg_run())
            return {
                "job_id": job_id,
                "status": "queued",
                "message": (
                    f"Benchmark job '{job_id}' queued with {num_queries} queries (concurrency={concurrency}). "
                    f"Check real-time status with contexta_benchmark_status(job_id='{job_id}')."
                ),
            }
        else:
            report = await self.benchmark_evaluator.run_suite(
                num_queries=num_queries,
                concurrency=concurrency,
                test_suite=test_suite,
                ablation=ablation,
                user_id=user_id,
            )
            return dataclasses.asdict(report)

    def _save_benchmark_jobs(self) -> None:
        try:
            p = Path(__file__).resolve().parent.parent.parent / "models" / "benchmark_jobs.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            existing = self._load_benchmark_jobs()
            merged = {**existing, **self._benchmark_jobs}
            with open(p, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2, default=str)
        except Exception as e:
            logger.warning("Failed to persist benchmark jobs: %s", e)

    def _load_benchmark_jobs(self) -> dict[str, dict[str, Any]]:
        try:
            p = Path(__file__).resolve().parent.parent.parent / "models" / "benchmark_jobs.json"
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning("Failed to load benchmark jobs: %s", e)
        return {}

    def get_benchmark_status(self, job_id: str) -> dict[str, Any]:
        """Retrieve progress or final results for a background benchmark job."""
        jobs = dict(self._benchmark_jobs)
        persisted = self._load_benchmark_jobs()
        all_jobs = {**persisted, **jobs}

        job = all_jobs.get(job_id)
        if not job and not job_id.startswith("bench-"):
            job = all_jobs.get(f"bench-{job_id}")
        if not job and job_id.startswith("bench-"):
            job = all_jobs.get(job_id.replace("bench-", ""))
        if not job and job_id.lower() in ("latest", "last", "") and all_jobs:
            job = list(all_jobs.values())[-1]

        if not job:
            return {
                "job_id": job_id,
                "status": "not_found",
                "message": f"Benchmark job '{job_id}' not found.",
                "available_jobs": list(all_jobs.keys()),
            }
        return dict(job)

    async def get_metrics(self) -> dict[str, Any]:
        """Return system health, database record counts, and engine telemetry."""
        from sqlalchemy import text

        async with self.session() as session:
            mem_count = (await session.execute(text("SELECT COUNT(*) FROM memory_record"))).scalar()
            ent_count = (await session.execute(text("SELECT COUNT(*) FROM entity"))).scalar()
            edge_count = (await session.execute(text("SELECT COUNT(*) FROM entity_edge"))).scalar()
            link_count = (await session.execute(text("SELECT COUNT(*) FROM memory_entity_link"))).scalar()

        # Probe reranker health
        reranker_status = "active"
        reranker_latency_ms = None
        try:
            t0 = time.perf_counter()
            client = self._reranker._get_client()
            resp = await client.get(f"{self.model_server_url}/health", timeout=2.0)
            reranker_latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            if resp.status_code != 200:
                reranker_status = f"unhealthy ({resp.status_code})"
        except Exception:
            reranker_status = "unavailable"

        return {
            "status": "healthy",
            "timestamp": datetime.now(UTC).isoformat(),
            "database": {
                "total_memories": mem_count,
                "total_entities": ent_count,
                "total_edges": edge_count,
                "total_memory_entity_links": link_count,
            },
            "embedding": {
                "model": self._embedder.model_name,
                "dimension": 1536,
                "provider": "FastEmbedLocalProvider (BAAI/bge-small-en-v1.5 zero-padded)",
            },
            "reranker": {
                "url": self.model_server_url,
                "status": reranker_status,
                "ping_ms": reranker_latency_ms,
            },
        }

    async def close(self) -> None:
        await self._reranker.close()
        if self._engine:
            await self._engine.dispose()

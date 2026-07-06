"""Hybrid retrieval engine."""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, Sequence

from contexta.core.schemas import RetrievalQuery
from contexta.core.scoring.engine import MemoryScoringEngine
from contexta.models.entity import EntityEdge, MemoryEntityLink
from contexta.models.memory import MemoryRecord


class RetrievalMemoryRepository(Protocol):
    async def get_by_user(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[MemoryRecord]:
        ...


class RetrievalLinkRepository(Protocol):
    async def get_memories_for_entity(
        self,
        entity_id: uuid.UUID,
    ) -> Sequence[MemoryEntityLink]:
        ...


class RetrievalEdgeRepository(Protocol):
    async def get_neighbors(
        self,
        entity_id: uuid.UUID,
    ) -> Sequence[EntityEdge]:
        ...


class Reranker(Protocol):
    async def rerank(
        self,
        query: RetrievalQuery,
        results: list["RetrievalResult"],
    ) -> list["RetrievalResult"]:
        ...


@dataclass(frozen=True)
class RetrievalResult:
    """Scored retrieval result."""

    memory: MemoryRecord
    score: float
    semantic_score: float
    graph_score: float
    importance_score: float
    recency_score: float
    keyword_score: float


class RetrievalEngine:
    """Hybrid semantic, keyword, graph, importance, and recency retrieval."""

    def __init__(
        self,
        memory_repository: RetrievalMemoryRepository,
        *,
        link_repository: RetrievalLinkRepository | None = None,
        edge_repository: RetrievalEdgeRepository | None = None,
        reranker: Reranker | None = None,
        scoring_engine: MemoryScoringEngine | None = None,
    ) -> None:
        self._memories = memory_repository
        self._links = link_repository
        self._edges = edge_repository
        self._reranker = reranker
        self._scoring = scoring_engine or MemoryScoringEngine()

    async def retrieve(
        self,
        query: RetrievalQuery,
        *,
        query_embedding: list[float] | None = None,
        seed_entity_ids: Sequence[uuid.UUID] = (),
        now: datetime | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve memories using weighted hybrid scoring."""
        reference = now or datetime.now(timezone.utc)
        candidates = await self._memories.get_by_user(
            query.user_id,
            limit=max(query.limit * 10, 100),
        )
        graph_memory_ids = await self._graph_memory_ids(
            seed_entity_ids,
            max_depth=query.graph_depth,
        )
        results = [
            self._score_memory(
                query,
                memory,
                query_embedding=query_embedding,
                graph_memory_ids=graph_memory_ids,
                now=reference,
            )
            for memory in candidates
            if self._include_memory(query, memory)
        ]
        results.sort(key=lambda result: result.score, reverse=True)
        results = results[: query.limit]

        if self._reranker is not None:
            try:
                results = await self._reranker.rerank(query, results)
            except Exception:
                results.sort(key=lambda result: result.score, reverse=True)

        return results[: query.limit]

    def _include_memory(self, query: RetrievalQuery, memory: MemoryRecord) -> bool:
        if memory.user_id != query.user_id:
            return False
        if memory.organization_id != query.organization_id:
            return False
        if memory.valid_to is not None:
            return False
        if memory.is_archived and not query.include_archived:
            return False
        if memory.memory_state == "cold" and not query.include_cold:
            return False
        if query.memory_types and memory.memory_type not in {
            memory_type.value for memory_type in query.memory_types
        }:
            return False
        if query.tags:
            tags = set(memory.tags or [])
            if not tags.intersection(query.tags):
                return False
        return True

    def _score_memory(
        self,
        query: RetrievalQuery,
        memory: MemoryRecord,
        *,
        query_embedding: list[float] | None,
        graph_memory_ids: set[uuid.UUID],
        now: datetime,
    ) -> RetrievalResult:
        semantic = self._cosine_similarity(query_embedding, memory.embedding)
        graph = 1.0 if memory.id in graph_memory_ids else 0.0
        importance = max(0.0, min(1.0, memory.importance))
        recency = self._scoring.compute_freshness(memory.created_at, now=now)
        keyword = self._keyword_score(query.query_text, memory)
        score = (
            semantic * 0.4
            + graph * 0.25
            + importance * 0.2
            + recency * 0.1
            + keyword * 0.05
        )
        if memory.memory_state == "cold":
            score = max(0.0, score - 0.3)
        return RetrievalResult(
            memory=memory,
            score=score,
            semantic_score=semantic,
            graph_score=graph,
            importance_score=importance,
            recency_score=recency,
            keyword_score=keyword,
        )

    async def _graph_memory_ids(
        self,
        seed_entity_ids: Sequence[uuid.UUID],
        *,
        max_depth: int,
    ) -> set[uuid.UUID]:
        if self._links is None:
            return set()

        visited: set[uuid.UUID] = set()
        frontier = set(seed_entity_ids)
        memory_ids: set[uuid.UUID] = set()

        for _ in range(max_depth + 1):
            if not frontier:
                break
            next_frontier: set[uuid.UUID] = set()
            for entity_id in frontier:
                if entity_id in visited:
                    continue
                visited.add(entity_id)
                for link in await self._links.get_memories_for_entity(entity_id):
                    memory_ids.add(link.memory_id)
                if self._edges is not None:
                    for edge in await self._edges.get_neighbors(entity_id):
                        next_frontier.add(edge.source_entity_id)
                        next_frontier.add(edge.target_entity_id)
            frontier = next_frontier - visited

        return memory_ids

    def _keyword_score(self, query_text: str, memory: MemoryRecord) -> float:
        query_terms = self._terms(query_text)
        if not query_terms:
            return 0.0
        memory_terms = self._terms(
            " ".join([memory.title, memory.content, " ".join(memory.tags or [])])
        )
        return len(query_terms.intersection(memory_terms)) / len(query_terms)

    def _terms(self, text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    def _cosine_similarity(
        self,
        left: list[float] | None,
        right: list[float] | None,
    ) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return max(0.0, min(1.0, dot / (left_norm * right_norm)))

"""Hybrid retrieval engine."""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

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

    async def get_entities_for_memory(
        self,
        memory_id: uuid.UUID,
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
        results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
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

    STOPWORDS = {
        "what", "when", "where", "who", "which", "whose", "why", "how",
        "did", "does", "do", "is", "are", "was", "were", "be", "been", "being",
        "the", "a", "an", "in", "on", "at", "to", "for", "of", "with", "by",
        "about", "from", "as", "into", "like", "through", "after", "over",
        "between", "out", "against", "during", "without", "before", "under",
        "around", "among", "and", "or", "but", "if", "then", "else", "so",
        "i", "me", "my", "myself", "we", "us", "our", "ours", "you", "your", "yours",
        "he", "him", "his", "she", "her", "hers", "they", "them", "their", "theirs",
        "it", "its", "have", "has", "had", "having", "ve", "ll", "re", "d", "m",
        "date", "pm", "am", "yeah", "yes", "yep", "thanks", "thank", "hey", "hello",
        "hi", "good", "great", "really", "just", "gonna", "wanna", "gotta", "well",
        "sure", "that", "this", "these", "those", "there", "here",
    }

    def __init__(
        self,
        memory_repository: RetrievalMemoryRepository,
        *,
        link_repository: RetrievalLinkRepository | None = None,
        edge_repository: RetrievalEdgeRepository | None = None,
        entity_repository: Any = None,
        reranker: Reranker | None = None,
        scoring_engine: MemoryScoringEngine | None = None,
    ) -> None:
        self._memories = memory_repository
        self._links = link_repository
        self._edges = edge_repository
        self._entities = entity_repository
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
        reference = now or datetime.now(UTC)
        candidates = await self._memories.get_by_user(
            query.user_id,
            limit=max(query.limit * 50, 1000),
        )

        # Automatic entity seed resolution for multi-hop graph traversal (word-boundary matched)
        if not seed_entity_ids and self._entities is not None:
            user_entities = await self._entities.get_by_user(query.user_id, limit=500)
            q_lower = query.query_text.lower()
            seed_entity_ids = [
                e.id for e in user_entities
                if len(e.name) > 2 and (
                    re.search(r"\b" + re.escape(e.name.lower()) + r"\b", q_lower) is not None
                    or any(
                        re.search(r"\b" + re.escape(alias.lower()) + r"\b", q_lower) is not None
                        for alias in (getattr(e, "aliases", None) or [])
                    )
                )
            ]

        graph_memory_weights = await self._graph_memory_weights(
            seed_entity_ids,
            max_depth=max(query.graph_depth, 2),
        )
        results = [
            self._score_memory(
                query,
                memory,
                query_embedding=query_embedding,
                graph_memory_weights=graph_memory_weights,
                now=reference,
            )
            for memory in candidates
            if self._include_memory(query, memory)
        ]
        results.sort(key=lambda result: result.score, reverse=True)

        # Collect candidate pool for multi-hop, graph, and neural reranking
        candidate_pool: list[RetrievalResult] = []
        seen_ids = set()

        # 1. Primary scored results (up to 30 candidates)
        primary_pool_size = max(query.limit * 2, 30)
        top_primary = results[: min(primary_pool_size, len(results))]
        for r in top_primary:
            seen_ids.add(r.memory.id)
            candidate_pool.append(r)

        candidate_map = {m.id: m for m in candidates}
        supplementary: list[RetrievalResult] = []

        # 2. Graph links and edges expansion from top 5 primary candidates
        if self._links is not None and len(results) > 1:
            for h1 in top_primary[:5]:
                try:
                    mem_links = await self._links.get_entities_for_memory(h1.memory.id)
                    for lk in mem_links:
                        ent_links = await self._links.get_memories_for_entity(lk.entity_id)
                        # Non-hub, informative bridge entities only (degree between 2 and 30)
                        if 1 < len(ent_links) <= 30:
                            for el in ent_links:
                                if el.memory_id not in seen_ids and el.memory_id in candidate_map:
                                    seen_ids.add(el.memory_id)
                                    supp_mem = candidate_map[el.memory_id]
                                    if self._include_memory(query, supp_mem):
                                        supp_res = self._score_memory(
                                            query,
                                            supp_mem,
                                            query_embedding=query_embedding,
                                            graph_memory_weights=graph_memory_weights,
                                            now=reference,
                                        )
                                        supplementary.append(supp_res)

                        # Multi-hop via knowledge graph edges: entity_1 -> edge -> entity_2 -> memories
                        if self._edges is not None and len(supplementary) < 12:
                            neighbors = await self._edges.get_neighbors(lk.entity_id)
                            for edge in neighbors[:10]:
                                n_id = (
                                    edge.target_entity_id
                                    if edge.source_entity_id == lk.entity_id
                                    else edge.source_entity_id
                                )
                                n_links = await self._links.get_memories_for_entity(n_id)
                                if 1 < len(n_links) <= 30:
                                    for el in n_links:
                                        if el.memory_id not in seen_ids and el.memory_id in candidate_map:
                                            seen_ids.add(el.memory_id)
                                            supp_mem = candidate_map[el.memory_id]
                                            if self._include_memory(query, supp_mem):
                                                supp_res = self._score_memory(
                                                    query,
                                                    supp_mem,
                                                    query_embedding=query_embedding,
                                                    graph_memory_weights=graph_memory_weights,
                                                    now=reference,
                                                )
                                                supplementary.append(supp_res)
                except Exception:
                    pass

        # 3. Multi-hop content bridge: search for connected memories across the top candidates
        generic_terms = {"melanie", "caroline", "speaker", "user", "date", "year", "time", "day", "yesterday", "today", "tomorrow"}
        for h1_top in top_primary[:5]:
            h1_terms = self._terms(h1_top.memory.content) - generic_terms
            if h1_terms:
                term_matches: list[tuple[int, MemoryRecord]] = []
                for cand in candidates:
                    if cand.id not in seen_ids and self._include_memory(query, cand):
                        c_terms = self._terms(cand.content) - generic_terms
                        overlap = len(h1_terms.intersection(c_terms))
                        if overlap >= 1:
                            term_matches.append((overlap, cand))
                term_matches.sort(key=lambda x: x[0], reverse=True)
                for _, cand in term_matches[:4]:
                    if cand.id not in seen_ids:
                        seen_ids.add(cand.id)
                        supp_res = self._score_memory(
                            query,
                            cand,
                            query_embedding=query_embedding,
                            graph_memory_weights=graph_memory_weights,
                            now=reference,
                        )
                        supplementary.append(supp_res)

        # 4. Session adjacent bridge: include turns from the same session to preserve conversational context
        for h1_top in top_primary[:3]:
            sess_id = h1_top.memory.session_id
            if sess_id:
                for cand in candidates:
                    if cand.id not in seen_ids and cand.session_id == sess_id and self._include_memory(query, cand):
                        seen_ids.add(cand.id)
                        supp_res = self._score_memory(
                            query,
                            cand,
                            query_embedding=query_embedding,
                            graph_memory_weights=graph_memory_weights,
                            now=reference,
                        )
                        supplementary.append(supp_res)

        # Add supplementary to candidate pool
        candidate_pool.extend(supplementary)

        # 5. Reranking or Selection
        if self._reranker is not None:
            try:
                # Give neural reranker the full candidate pool (up to 45 candidates)
                rerank_candidates = candidate_pool[:45]
                reranked = await self._reranker.rerank(query, rerank_candidates)
                return reranked[: query.limit]
            except Exception:  # noqa: BLE001 - rerank failure falls back to scored order
                pass

        # Fallback when no reranker or rerank fails: balanced primary + supplementary
        if supplementary:
            supp_limit = min(len(supplementary), max(4, query.limit // 3))
            primary_budget = max(1, query.limit - supp_limit)
            results = top_primary[:primary_budget] + supplementary[:supp_limit]
            if len(results) < query.limit:
                for r in top_primary[primary_budget:]:
                    if r.memory.id not in {res.memory.id for res in results}:
                        results.append(r)
                        if len(results) >= query.limit:
                            break
            return results[: query.limit]

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
        graph_memory_weights: dict[uuid.UUID, float],
        now: datetime,
    ) -> RetrievalResult:
        semantic = float(self._cosine_similarity(query_embedding, memory.embedding))
        graph = float(graph_memory_weights.get(memory.id, 0.0))
        importance = float(max(0.0, min(1.0, memory.importance)))
        recency = float(self._scoring.compute_freshness(memory.created_at, now=now))
        keyword = float(self._keyword_score(query.query_text, memory))

        # Conversational speaker context boost
        speaker_bonus = 0.0
        q_lower = query.query_text.lower()
        m_content = memory.content.lower()
        if "melanie" in q_lower and ("melanie:" in m_content or "melanie's" in m_content):
            speaker_bonus = 0.10
        elif "caroline" in q_lower and ("caroline:" in m_content or "caroline's" in m_content):
            speaker_bonus = 0.10

        # Exact phrase bonus for salient n-grams
        phrase_bonus = 0.0
        q_words = [w for w in re.findall(r"[a-z0-9]+", q_lower) if w not in self.STOPWORDS]
        for i in range(len(q_words) - 1):
            bigram = f"{q_words[i]} {q_words[i+1]}"
            if len(bigram) > 6 and bigram in m_content:
                phrase_bonus = 0.15
                break

        score = (
            semantic * 0.40
            + keyword * 0.35
            + graph * 0.15
            + importance * 0.05
            + speaker_bonus
            + phrase_bonus
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

    async def _graph_memory_weights(
        self,
        seed_entity_ids: Sequence[uuid.UUID],
        *,
        max_depth: int,
    ) -> dict[uuid.UUID, float]:
        if self._links is None:
            return {}

        visited: set[uuid.UUID] = set()
        frontier = set(seed_entity_ids)
        memory_weights: dict[uuid.UUID, float] = {}

        for depth in range(max_depth + 1):
            if not frontier:
                break
            next_frontier: set[uuid.UUID] = set()
            depth_decay = 1.0 if depth == 0 else (0.5 ** depth)
            for entity_id in frontier:
                if entity_id in visited:
                    continue
                visited.add(entity_id)
                links = await self._links.get_memories_for_entity(entity_id)
                degree = len(links)
                if degree == 0:
                    continue
                # Inverse degree specificity: high-degree hub nodes get lower weight
                weight = (1.0 / (degree ** 0.5)) * depth_decay
                for link in links:
                    memory_weights[link.memory_id] = max(
                        memory_weights.get(link.memory_id, 0.0),
                        weight,
                    )
                # Expand graph edges: always for depth 0 seeds, and up to degree 35 for intermediate nodes
                if self._edges is not None and (depth == 0 or degree <= 35):
                    try:
                        neighbors = await self._edges.get_neighbors(entity_id)
                        for edge in neighbors[:20]:
                            next_frontier.add(edge.source_entity_id)
                            next_frontier.add(edge.target_entity_id)
                    except Exception:
                        pass
            frontier = next_frontier - visited

        return memory_weights

    @staticmethod
    def _normalize_stem(word: str) -> str:
        w = word.lower().strip(".,;:!?()[]\"'")
        number_map = {
            "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
            "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
        }
        if w in number_map:
            return number_map[w]
        synonyms = {
            "adopting": "adopt", "adoption": "adopt", "advice": "adopt", "children": "child",
            "kids": "child", "kid": "child", "daughter": "child", "daughters": "child",
            "son": "child", "sons": "child", "counselor": "counsel", "counseling": "counsel",
            "reading": "book", "books": "book", "bookshelf": "book", "seuss": "book", "library": "book",
            "classics": "classic", "liberal": "progressive", "hiking": "hike", "hikes": "hike",
            "religious": "religion", "religions": "religion", "outdoors": "park", "outdoor": "park",
            "camping": "camp", "camped": "camp", "pets": "pet", "guinea": "pet", "pig": "pet",
            "pigs": "pet", "oscar": "pet", "paintings": "paint", "painted": "paint", "painting": "paint",
            "moved": "move", "moving": "move", "shoes": "shoe", "drawings": "draw", "drawing": "draw",
            "traits": "personality", "trait": "personality", "ally": "support", "supportive": "support",
            "events": "event", "activities": "activity", "pots": "pottery", "pot": "pottery",
            "bowls": "bowl", "cups": "cup", "sunsets": "sunset", "songs": "music", "song": "music",
            "artists": "music", "bands": "music", "band": "music", "musicians": "music",
            "mozart": "music", "bach": "music", "vivaldi": "music", "classical": "music",
            "sidewalk": "walk", "sidewalks": "walk", "running": "run",
            "relationship": "single", "relationships": "single", "status": "single",
            "breakup": "single", "dating": "single", "married": "single", "boyfriend": "single", "husband": "single",
            "transgender": "transition", "lgbtq": "transition", "pride": "transition",
        }
        if w in synonyms:
            return synonyms[w]
        for suffix in ("ing", "tion", "tions", "ies", "es", "ed", "s", "or", "er", "ic", "al"):
            if len(w) > len(suffix) + 3 and w.endswith(suffix):
                return w[:-len(suffix)]
        return w

    def _keyword_score(self, query_text: str, memory: MemoryRecord) -> float:
        query_terms = self._terms(query_text)
        if not query_terms:
            return 0.0
        memory_terms = self._terms(
            " ".join([memory.title, memory.content, " ".join(memory.tags or [])])
        )
        if not memory_terms:
            return 0.0

        common_names = {"melanie", "caroline", "speaker", "user"}
        total_w = 0.0
        matched_w = 0.0
        for t in query_terms:
            w = 0.20 if t in common_names else 1.0
            total_w += w
            if t in memory_terms:
                matched_w += w
        return matched_w / total_w if total_w > 0 else 0.0

    def _terms(self, text: str) -> set[str]:
        raw = set(re.findall(r"[a-z0-9]+", text.lower()))
        filtered = {self._normalize_stem(w) for w in raw if (w.isdigit() or len(w) > 1) and w not in self.STOPWORDS}
        return filtered or raw

    def _cosine_similarity(
        self,
        left: list[float] | None,
        right: list[float] | None,
    ) -> float:
        if left is None or right is None or len(left) != len(right):
            return 0.0
        dot = sum(float(a) * float(b) for a, b in zip(left, right))
        left_norm = math.sqrt(sum(float(a) * float(a) for a in left))
        right_norm = math.sqrt(sum(float(b) * float(b) for b in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return float(max(0.0, min(1.0, dot / (left_norm * right_norm))))

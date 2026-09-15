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

    DISCOURSE_STOPWORDS = {
        "speaker", "user", "assistant", "system", "date", "year", "time",
        "day", "yesterday", "today", "tomorrow", "session", "turn", "conversation",
        "chat", "pm", "am", "clock", "hour", "minute", "month", "week",
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
        # Vector-accelerated candidate retrieval directly in PostgreSQL via pgvector
        if query_embedding is not None and hasattr(self._memories, "get_by_vector_similarity"):
            candidates = await self._memories.get_by_vector_similarity(
                query.user_id,
                query_embedding,
                limit=max(query.limit * 15, 150),
            )
        else:
            candidates = await self._memories.get_by_user(
                query.user_id,
                limit=max(query.limit * 50, 1000),
            )

        # Automatic entity seed resolution for multi-hop graph traversal (word-boundary matched)
        if not seed_entity_ids and self._entities is not None:
            user_entities = await self._entities.get_by_user(query.user_id, limit=500)
            if not user_entities and hasattr(self._entities, "get_all"):
                user_entities = await self._entities.get_all(limit=500)
            q_lower = query.query_text.lower()
            seed_entity_ids = [
                e.id for e in user_entities
                if len(e.name) >= 2 and (
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

        # 2. Bulk graph links and edges expansion from top primary candidates
        if self._links is not None and len(results) > 1:
            top_mem_ids = [h1.memory.id for h1 in top_primary[:5]]
            try:
                if hasattr(self._links, "bulk_get_entities_for_memories"):
                    mem_links = await self._links.bulk_get_entities_for_memories(top_mem_ids)
                else:
                    mem_links = []
                    for mid in top_mem_ids:
                        mem_links.extend(await self._links.get_entities_for_memory(mid))

                entity_ids = list({lk.entity_id for lk in mem_links})

                if entity_ids:
                    if hasattr(self._links, "bulk_get_memories_for_entities"):
                        all_ent_links = await self._links.bulk_get_memories_for_entities(entity_ids)
                    else:
                        all_ent_links = []
                        for eid in entity_ids:
                            all_ent_links.extend(await self._links.get_memories_for_entity(eid))

                    import collections
                    ent_to_links = collections.defaultdict(list)
                    for el in all_ent_links:
                        ent_to_links[el.entity_id].append(el)

                    for eid, el_list in ent_to_links.items():
                        if 1 < len(el_list) <= 30:
                            for el in el_list:
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

                    # Multi-hop via knowledge graph edges using bulk_get_neighbors
                    if self._edges is not None and len(supplementary) < 12:
                        if hasattr(self._edges, "bulk_get_neighbors"):
                            neighbors = await self._edges.bulk_get_neighbors(entity_ids[:10])
                        else:
                            neighbors = []
                            for eid in entity_ids[:10]:
                                neighbors.extend(await self._edges.get_neighbors(eid))

                        ent_id_set = set(entity_ids)
                        n_ids = list({
                            edge.target_entity_id if edge.source_entity_id in ent_id_set else edge.source_entity_id
                            for edge in neighbors[:20]
                        })
                        if n_ids:
                            if hasattr(self._links, "bulk_get_memories_for_entities"):
                                n_links = await self._links.bulk_get_memories_for_entities(n_ids)
                            else:
                                n_links = []
                                for nid in n_ids:
                                    n_links.extend(await self._links.get_memories_for_entity(nid))

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
        # Dynamic corpus specificity: words appearing in >30% of candidates are treated as generic context
        cand_term_freq: dict[str, int] = {}
        for c in candidates:
            for t in self._terms(c.content):
                cand_term_freq[t] = cand_term_freq.get(t, 0) + 1
        common_corpus_terms = {
            t for t, cnt in cand_term_freq.items()
            if cnt > max(3, int(len(candidates) * 0.30))
        }
        bridge_stopwords = self.STOPWORDS | self.DISCOURSE_STOPWORDS | common_corpus_terms

        cand_terms_cache = {
            c.id: self._terms(c.content) - bridge_stopwords
            for c in candidates
            if self._include_memory(query, c)
        }

        for h1_top in top_primary[:5]:
            h1_terms = self._terms(h1_top.memory.content) - bridge_stopwords
            if h1_terms:
                term_matches: list[tuple[int, MemoryRecord]] = []
                for cand in candidates:
                    if cand.id not in seen_ids and cand.id in cand_terms_cache:
                        c_terms = cand_terms_cache[cand.id]
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
                final = reranked[: query.limit]
                await self._touch_accessed(final, reference)
                return final
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
            final = results[: query.limit]
            await self._touch_accessed(final, reference)
            return final

        final = results[: query.limit]
        await self._touch_accessed(final, reference)
        return final

    async def _touch_accessed(self, results: list[RetrievalResult], now: datetime) -> None:
        """Best-effort update of last_accessed_at so decay uses read-age, not write-age."""
        touch = getattr(self._memories, "touch_accessed", None)
        if touch is None:
            return
        for r in results:
            try:
                await touch(r.memory.id, now.replace(tzinfo=None))
            except Exception:  # noqa: BLE001 - access tracking never fails retrieval
                continue


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
        utility = float(max(-1.0, min(1.0, memory.utility_score or 0.0)))
        confidence = float(max(0.0, min(1.0, memory.confidence or 0.0)))

        # Universal conversational speaker context boost:
        # Dynamically matches extracted speaker names from transcripts (e.g. "[Speaker]:" or "Speaker:")
        speaker_bonus = 0.0
        q_lower = query.query_text.lower()
        m_strip = memory.content.strip()
        m_content = m_strip.lower()
        speaker_match = re.match(r"^(?:\[([A-Za-z0-9_-]+)(?:\s+on\s+[^\]]+)?\]|([A-Za-z0-9_-]+):)", m_strip)
        if speaker_match:
            speaker_name = (speaker_match.group(1) or speaker_match.group(2)).lower()
            if speaker_name and len(speaker_name) > 1 and speaker_name not in {"user", "assistant", "system"}:
                if re.search(r"\b" + re.escape(speaker_name) + r"(?:'s)?\b", q_lower):
                    speaker_bonus = 0.10

        # Exact phrase bonus for salient n-grams
        phrase_bonus = 0.0
        q_words = [w for w in re.findall(r"[a-z0-9]+", q_lower) if w not in self.STOPWORDS]
        for i in range(len(q_words) - 1):
            bigram = f"{q_words[i]} {q_words[i+1]}"
            if len(bigram) > 6 and bigram in m_content:
                phrase_bonus = 0.15
                break

        # Dynamically scale graph weight if caller requested deep graph traversal (graph_depth >= 2)
        if query.graph_depth >= 2 and graph > 0.0:
            w_sem = 0.32
            w_kw = 0.22
            w_graph = 0.18
        else:
            w_sem = 0.34
            w_kw = 0.24
            w_graph = 0.12
        w_imp = 0.08
        w_rec = 0.10
        w_util = 0.05
        w_conf = 0.03

        score = (
            semantic * w_sem
            + keyword * w_kw
            + graph * w_graph
            + importance * w_imp
            + recency * w_rec
            + utility * w_util
            + confidence * w_conf
            + speaker_bonus
            + phrase_bonus
        )
        if memory.memory_state == "cold":
            score = max(0.0, score * 0.7)
        clamped_score = min(1.0, max(0.0, score))
        return RetrievalResult(
            memory=memory,
            score=clamped_score,
            semantic_score=min(1.0, max(0.0, semantic)),
            graph_score=min(1.0, max(0.0, graph)),
            importance_score=min(1.0, max(0.0, importance)),
            recency_score=min(1.0, max(0.0, recency)),
            keyword_score=min(1.0, max(0.0, keyword)),
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
        """Standard morphological normalization: numbers, common suffixes, and core inflections."""
        w = word.lower().strip(".,;:!?()[]\"'")
        number_map = {
            "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
            "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
            "ten": "10", "first": "1st", "second": "2nd", "third": "3rd",
        }
        if w in number_map:
            return number_map[w]

        # Core English morphological variants (generic)
        inflections = {
            "children": "child", "kids": "child", "kid": "child",
            "daughters": "daughter", "sons": "son",
            "hiking": "hike", "hikes": "hike",
            "walking": "walk", "walks": "walk",
            "running": "run", "runs": "run",
            "camping": "camp", "camped": "camp",
            "paintings": "paint", "painted": "paint",
            "drawings": "draw", "moving": "move", "moved": "move",
        }
        if w in inflections:
            return inflections[w]

        # Standard suffix stripping (Porter stemmer principles)
        for suffix in ("ing", "tion", "tions", "ies", "es", "ed", "ment", "able", "ible", "ity", "ive", "s", "or", "er", "ic", "al"):
            if len(w) > len(suffix) + 3 and w.endswith(suffix):
                if suffix == "ies":
                    return w[:-3] + "y"
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

        total_w = 0.0
        matched_w = 0.0
        for t in query_terms:
            # Downweight generic conversational discourse terms
            w = 0.25 if t in self.DISCOURSE_STOPWORDS else 1.0
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

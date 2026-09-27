"""Hybrid retrieval engine."""

from __future__ import annotations

import inspect
import math
import re
import uuid
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from contexta.config.settings import get_settings
from contexta.core.cortex import ContextaCortex, CortexReadDecision
from contexta.core.retrieval.fusion import (
    SufficiencyAssessment,
    assess_primary_sufficiency,
    weighted_reciprocal_rank_fusion,
)
from contexta.core.retrieval.query_understanding import QueryPlan, build_query_plan
from contexta.models.memory import MemoryRecord

if TYPE_CHECKING:
    from contexta.core.schemas import RetrievalQuery

try:
    from contexta.core.scoring.engine import (
        MemoryScoringEngine,
        compute_precision_aware_freshness,
    )
except NameError:
    def compute_precision_aware_freshness(
        occurred_at: datetime,
        *,
        now: datetime | None = None,
        temporal_precision: str | None = None,
        temporal_basis: str | None = None,
        base_half_life_days: float = 3650.0,
    ) -> float:
        """Degraded stand-in: identical to `compute_freshness`, precision ignored."""
        reference = now or datetime.now(UTC)
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=UTC)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        age_days = max((reference - occurred_at).total_seconds(), 0.0) / 86400
        if base_half_life_days <= 0:
            base_half_life_days = 30.0
        return math.exp(-math.log(2) * age_days / base_half_life_days)

    class MemoryScoringEngine:
        def compute_freshness(
            self,
            created_at: datetime,
            *,
            now: datetime | None = None,
            half_life_days: float = 30.0,
        ) -> float:
            reference = now or datetime.now(UTC)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            if reference.tzinfo is None:
                reference = reference.replace(tzinfo=UTC)
            age_days = max((reference - created_at).total_seconds(), 0.0) / 86400
            if half_life_days <= 0:
                half_life_days = 30.0
            return math.exp(-math.log(2) * age_days / half_life_days)

        def compute_precision_aware_freshness(
            self,
            occurred_at: datetime,
            *,
            now: datetime | None = None,
            temporal_precision: str | None = None,
            temporal_basis: str | None = None,
            base_half_life_days: float = 3650.0,
        ) -> float:
            return compute_precision_aware_freshness(
                occurred_at,
                now=now,
                temporal_precision=temporal_precision,
                temporal_basis=temporal_basis,
                base_half_life_days=base_half_life_days,
            )


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
    async def walk_entity_graph(
        self,
        *,
        seed_entity_ids: Sequence[uuid.UUID],
        max_depth: int = 2,
        max_nodes: int = 200,
        max_neighbors_per_node: int = 20,
    ) -> dict[uuid.UUID, int]:
        """Return `{entity_id: hop distance}` for everything within the cap.

        One recursive CTE with a hard frontier cap, a per-node neighbour cap and
        tenant scoping in every hop, replacing the per-node BFS this used to run
        (`1 + 2 * nodes` round trips, unbounded frontier).
        """
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
    query_plan: QueryPlan | None = field(default=None, compare=False)
    # Precomputed lowercased entity names this result's text mentions. Carried
    # so the sufficiency gate can read plan coverage without re-scanning text,
    # and excluded from equality: it is derived, `replace()` copies it, and it
    # is only populated on the cascade path (the gate is its only consumer).
    mentioned_entities: frozenset[str] = field(
        default_factory=frozenset,
        compare=False,
    )

    @property
    def evidence_id(self) -> str:
        return str(self.memory.id)


@dataclass(frozen=True)
class CascadeEscalation:
    """What the cascade decided for one retrieval, and why.

    Populated on `RetrievalEngine.last_escalation`. `escalated` is False both
    when escalation is disabled (the default) and when the gate said the
    primary channels were enough; `enabled` distinguishes them.
    """

    enabled: bool
    escalated: bool
    reason: str
    dense_candidates: int = 0
    fused_candidates: int = 0
    assessment: SufficiencyAssessment | None = None


class RetrievalEngine:
    """Hybrid semantic, keyword, graph, importance, and recency retrieval."""

    CANDIDATE_MULTIPLIER = 15
    MIN_CANDIDATES = 150
    RERANK_POOL_SIZE = 45
    TEMPORAL_CANDIDATE_UPLIFT = 1.5
    # Base half-lives for the two freshness terms, in days. Both are stretched
    # by `precision_half_life_scale` according to the fact's
    # `temporal_precision`, and both contribute a bounded weight to the score
    # (w_rec below, and the 0.12 multiplier on `_temporal_relevance`), so the
    # stretch cannot make freshness dominate.
    RECENCY_HALF_LIFE_DAYS = 30.0
    TEMPORAL_HALF_LIFE_DAYS = 3650.0
    FUSION_QUALITY_PRIOR = 0.20
    DEFAULT_CHANNEL_WEIGHTS = {
        "dense": 0.5,
        "lexical": 0.3,
        "graph": 0.2,
    }

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

    ENTITY_STOPWORDS = STOPWORDS | {
        "both", "common", "compare", "comparison", "difference", "differences",
        "shared", "similar", "intersection", "overlap", "versus", "vs", "list",
        "each", "all", "beginning", "event", "events", "project", "kind", "type",
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december", "same", "similarities",
        "commonalities",
    }

    COMPARATIVE_MARKERS = {
        "both", "common", "compare", "comparison", "difference", "differences",
        "shared", "similar", "intersection", "overlap", "versus", "vs", "list",
        "each", "all", "same", "similarities", "commonalities",
    }

    MONTH_NAMES = (
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
    )

    def __init__(
        self,
        memory_repository: RetrievalMemoryRepository,
        *,
        link_repository: RetrievalLinkRepository | None = None,
        edge_repository: RetrievalEdgeRepository | None = None,
        entity_repository: Any = None,
        reranker: Reranker | None = None,
        scoring_engine: MemoryScoringEngine | None = None,
        cortex: ContextaCortex | None = None,
        enable_dense_escalation: bool = False,
    ) -> None:
        self._memories = memory_repository
        self._links = link_repository
        self._edges = edge_repository
        self._entities = entity_repository
        self._reranker = reranker
        self._scoring = scoring_engine or MemoryScoringEngine()
        self._cortex = cortex
        # Default False: dense is fetched up front and always fused, exactly as
        # before the cascade existed. Flip it on to make lexical + graph the
        # primary channels and dense an escalation the sufficiency gate has to
        # earn. See `assess_primary_sufficiency` for the signal and
        # `last_escalation` for how to measure it.
        self._enable_dense_escalation = enable_dense_escalation
        # Observability only, set once per `retrieve()`. It exists so the
        # escalation rate can be measured in production before the cascade is
        # relied on; nothing branches on it, and concurrent retrieves may
        # interleave writes to it.
        self.last_escalation: CascadeEscalation | None = None

    async def retrieve(
        self,
        query: RetrievalQuery,
        *,
        query_embedding: list[float] | None = None,
        seed_entity_ids: Sequence[uuid.UUID] = (),
        query_plan: QueryPlan | None = None,
        plan: QueryPlan | None = None,
        now: datetime | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve memories using weighted hybrid scoring."""
        reference = query.as_of or now or datetime.now(UTC)
        cortex_decision: CortexReadDecision | None = None
        if self._cortex is not None and getattr(self._cortex, "is_enabled", False):
            with suppress(Exception):
                cortex_decision = await self._cortex.classify_query(query)

        known_entities: list[Any] = []
        if self._entities is not None:
            get_by_user = getattr(self._entities, "get_by_user", None)
            if callable(get_by_user):
                with suppress(Exception):
                    known_entities = list(await get_by_user(query.user_id, limit=500) or [])
            if not known_entities:
                get_all = getattr(self._entities, "get_all", None)
                if callable(get_all):
                    with suppress(Exception):
                        known_entities = list(await get_all(limit=500) or [])
        if query_plan is None:
            query_plan = plan
        if query_plan is None:
            query_plan = build_query_plan(
                query.query_text,
                known_entities=known_entities,
                now=reference,
            )
        coverage_target = max(query.limit, query_plan.retrieval_limit_hint)
        result_limit = max(query.limit, query_plan.required_evidence_count)
        candidate_limit = max(
            coverage_target * self.CANDIDATE_MULTIPLIER,
            self.MIN_CANDIDATES,
        )
        if query_plan.explicit_temporal_constraints:
            # The temporal constraint is still applied in Python after fusion, so
            # widen the candidate pool first. Without this, rows that fail the
            # window are dropped from an already-capped pool and the result set
            # develops holes that nothing back-fills.
            candidate_limit = max(
                int(candidate_limit * self.TEMPORAL_CANDIDATE_UPLIFT),
                self.MIN_CANDIDATES,
            )
        dense_candidates: list[MemoryRecord] = []
        if self._enable_dense_escalation:
            # Cascade: lexical is the primary channel, and the graph expansion
            # anchors off it. Dense is held back until the gate says otherwise.
            lexical_candidates, _ = await self._lexical_candidates(
                query,
                limit=candidate_limit,
                fallback_memories=None,
            )
        else:
            dense_candidates, fallback_memories = await self._dense_candidates(
                query,
                query_embedding,
                limit=candidate_limit,
            )
            lexical_candidates, fallback_memories = await self._lexical_candidates(
                query,
                limit=candidate_limit,
                fallback_memories=fallback_memories,
            )

        detected_entity_names = [
            *query_plan.entities,
            *self._query_named_entities(query.query_text),
        ]
        q_lower = query.query_text.casefold()
        for entity in known_entities:
            names = [
                getattr(entity, "name", ""),
                *(getattr(entity, "aliases", None) or []),
            ]
            for name in names:
                if isinstance(name, str) and re.search(
                    rf"(?<!\w){re.escape(name.casefold())}(?!\w)", q_lower
                ):
                    detected_entity_names.append(name)
        detected_entity_names = list(
            dict.fromkeys(
                name.casefold()
                for name in detected_entity_names
                if isinstance(name, str) and name
            )
        )

        resolved_seed_ids = list(seed_entity_ids)
        if self._entities is not None:
            for entity in known_entities:
                names = [
                    getattr(entity, "name", ""),
                    *(getattr(entity, "aliases", None) or []),
                ]
                if any(
                    isinstance(name, str)
                    and re.search(rf"(?<!\w){re.escape(name.casefold())}(?!\w)", q_lower)
                    for name in names
                ):
                    identifier = getattr(entity, "id", None)
                    if identifier is not None:
                        resolved_seed_ids.append(identifier)
        if query_plan.entity_ids:
            for identifier in query_plan.entity_ids:
                with suppress(ValueError, TypeError):
                    resolved_seed_ids.append(uuid.UUID(str(identifier)))
        resolved_seed_ids = list(dict.fromkeys(resolved_seed_ids))

        effective_graph_depth = max(query.graph_depth, query_plan.graph_depth)
        if cortex_decision and cortex_decision.requires_graph:
            effective_graph_depth = max(effective_graph_depth, 3)
        if (
            len(detected_entity_names) >= 2
            and self._is_comparative_or_list_query(query.query_text)
        ):
            effective_graph_depth = max(effective_graph_depth, 2)

        # Anchor order is dense-then-lexical, which is what `_graph_channel`
        # encodes: the graph widens from the top five of each channel.
        if self._enable_dense_escalation:
            graph_memory_weights, graph_candidates = await self._graph_channel(
                query,
                resolved_seed_ids,
                effective_graph_depth,
                dense_candidates=(),
                lexical_candidates=lexical_candidates,
                limit=candidate_limit,
            )
            primary_results = self._fuse_and_score(
                {
                    "lexical": lexical_candidates,
                    "graph": graph_candidates,
                },
                query,
                query_embedding=query_embedding,
                graph_memory_weights=graph_memory_weights,
                now=reference,
                cortex_decision=cortex_decision,
                query_plan=query_plan,
                entity_names=detected_entity_names,
            )
            assessment = assess_primary_sufficiency(
                results=primary_results,
                plan=query_plan,
                required_entity_names=detected_entity_names,
            )
            if assessment.sufficient:
                results = primary_results
                self.last_escalation = CascadeEscalation(
                    enabled=True,
                    escalated=False,
                    reason=assessment.reason,
                    fused_candidates=len(results),
                    assessment=assessment,
                )
            else:
                # Escalate: fetch dense and re-fuse over all three channels.
                # The primary results are inputs to the new ranking, not
                # casualties of it -- every channel is re-fused from its own
                # candidate list, so nothing the lexical or graph pass found is
                # discarded.
                dense_candidates, _ = await self._dense_candidates(
                    query,
                    query_embedding,
                    limit=candidate_limit,
                )
                graph_memory_weights, graph_candidates = await self._graph_channel(
                    query,
                    resolved_seed_ids,
                    effective_graph_depth,
                    dense_candidates=dense_candidates,
                    lexical_candidates=lexical_candidates,
                    limit=candidate_limit,
                )
                results = self._fuse_and_score(
                    {
                        "dense": dense_candidates,
                        "lexical": lexical_candidates,
                        "graph": graph_candidates,
                    },
                    query,
                    query_embedding=query_embedding,
                    graph_memory_weights=graph_memory_weights,
                    now=reference,
                    cortex_decision=cortex_decision,
                    query_plan=query_plan,
                    entity_names=detected_entity_names,
                )
                self.last_escalation = CascadeEscalation(
                    enabled=True,
                    escalated=True,
                    reason=assessment.reason,
                    dense_candidates=len(dense_candidates),
                    fused_candidates=len(results),
                    assessment=assessment,
                )
        else:
            graph_memory_weights, graph_candidates = await self._graph_channel(
                query,
                resolved_seed_ids,
                effective_graph_depth,
                dense_candidates=dense_candidates,
                lexical_candidates=lexical_candidates,
                limit=candidate_limit,
            )
            results = self._fuse_and_score(
                {
                    "dense": dense_candidates,
                    "lexical": lexical_candidates,
                    "graph": graph_candidates,
                },
                query,
                query_embedding=query_embedding,
                graph_memory_weights=graph_memory_weights,
                now=reference,
                cortex_decision=cortex_decision,
                query_plan=query_plan,
            )
            self.last_escalation = CascadeEscalation(
                enabled=False,
                escalated=True,
                reason="escalation_disabled",
                dense_candidates=len(dense_candidates),
                fused_candidates=len(results),
            )

        results.sort(key=lambda result: result.score, reverse=True)
        if query_plan.explicit_temporal_constraints:
            results = [
                result
                for result in results
                if self._temporal_relevance(
                    query,
                    result.memory,
                    reference,
                    query_plan=query_plan,
                ) > 0.0
            ]

        if self._reranker is not None and results:
            rerank_pool_size = max(
                self.RERANK_POOL_SIZE,
                query_plan.retrieval_limit_hint,
            )
            rerank_pool = self._ensure_required_evidence(
                results[:rerank_pool_size],
                results,
                query_plan.required_evidence_ids,
            )
            reranked: list[RetrievalResult] = []
            with suppress(Exception):
                reranked = await self._reranker.rerank(
                    query,
                    rerank_pool,
                )
            if reranked:
                results = sorted(
                    [replace(result, query_plan=result.query_plan or query_plan) for result in reranked],
                    key=lambda result: result.score,
                    reverse=True,
                )

        final = self._promote_entity_coverage(
            query,
            results,
            entity_names=detected_entity_names,
            query_plan=query_plan,
            result_limit=result_limit,
        )[:result_limit]
        await self._touch_accessed(final, reference)
        return final

    async def _graph_channel(
        self,
        query: RetrievalQuery,
        seed_entity_ids: Sequence[uuid.UUID],
        effective_graph_depth: int,
        *,
        dense_candidates: Sequence[MemoryRecord],
        lexical_candidates: Sequence[MemoryRecord],
        limit: int,
    ) -> tuple[dict[uuid.UUID, float], list[MemoryRecord]]:
        """Expand from the seeds, then widen from the top five of each channel.

        Anchors are the best five from each channel rather than the best five
        overall: the two channels are independent evidence, so a page that is
        all-dense and a page that is all-lexical both have to be able to pull
        the graph outward. The expansion runs one hop deeper than the seed walk.
        """
        graph_memory_weights = await self._graph_memory_weights(
            seed_entity_ids,
            max_depth=max(effective_graph_depth, 0),
        )
        anchor_ids = list(
            dict.fromkeys(
                memory.id
                for memory in [*dense_candidates[:5], *lexical_candidates[:5]]
            )
        )
        expansion_entities = await self._entity_ids_for_memories(anchor_ids)
        if expansion_entities:
            expanded_weights = await self._graph_memory_weights(
                expansion_entities,
                max_depth=max(effective_graph_depth, 1),
            )
            for memory_id, weight in expanded_weights.items():
                graph_memory_weights[memory_id] = max(
                    graph_memory_weights.get(memory_id, 0.0),
                    weight,
                )
        graph_candidates = await self._graph_candidates(
            query,
            graph_memory_weights,
            known_memories=[*dense_candidates, *lexical_candidates],
            limit=limit,
        )
        return graph_memory_weights, graph_candidates

    def _fuse_and_score(
        self,
        channels: dict[str, Sequence[MemoryRecord]],
        query: RetrievalQuery,
        *,
        query_embedding: list[float] | None,
        graph_memory_weights: dict[uuid.UUID, float],
        now: datetime,
        cortex_decision: CortexReadDecision | None = None,
        query_plan: QueryPlan | None = None,
        entity_names: Sequence[str] = (),
    ) -> list[RetrievalResult]:
        """One RRF over the named channels, then a feature score per survivor.

        A channel absent from `channels` is simply not fused, and RRF
        renormalises against the weights that are active, so the two-channel
        primary pass is scored on the same scale as the three-channel one.
        """
        return self._score_candidates(
            weighted_reciprocal_rank_fusion(
                channels,
                weights=self._channel_weights(cortex_decision),
                quality_prior=self.FUSION_QUALITY_PRIOR,
            ),
            query,
            query_embedding=query_embedding,
            graph_memory_weights=graph_memory_weights,
            now=now,
            cortex_decision=cortex_decision,
            query_plan=query_plan,
            entity_names=entity_names,
        )

    def _score_candidates(
        self,
        fused_candidates: Sequence[Any],
        query: RetrievalQuery,
        *,
        query_embedding: list[float] | None,
        graph_memory_weights: dict[uuid.UUID, float],
        now: datetime,
        cortex_decision: CortexReadDecision | None = None,
        query_plan: QueryPlan | None = None,
        entity_names: Sequence[str] = (),
    ) -> list[RetrievalResult]:
        """Blend each fused rank with the memory's own feature score.

        `entity_names` is the caller's detected entity list, and what a
        candidate mentions in it is cached on the result so the sufficiency gate
        can read plan coverage without re-scanning text. Pass `()` when no gate
        will read it: the scan is a regex per name over title, content, tags and
        structured data, and the candidate pool is two orders of magnitude
        larger than the page. The scan also stops as soon as every name has been
        seen, since later candidates cannot add coverage.
        """
        pending = set(entity_names)
        results: list[RetrievalResult] = []
        for candidate in fused_candidates:
            base_result = self._score_memory(
                query,
                candidate.memory,
                query_embedding=query_embedding,
                graph_memory_weights=graph_memory_weights,
                now=now,
                cortex_decision=cortex_decision,
                query_plan=query_plan,
            )
            fused_score = 0.80 * candidate.score + 0.20 * base_result.score
            if candidate.memory.memory_state == "cold":
                fused_score *= 0.7
            mentioned = (
                self._mentioned_entities(candidate.memory, pending)
                if pending
                else frozenset()
            )
            pending.difference_update(mentioned)
            results.append(
                replace(
                    base_result,
                    score=min(1.0, max(0.0, fused_score)),
                    mentioned_entities=mentioned,
                )
            )
        return results

    def _mentioned_entities(
        self,
        memory: MemoryRecord,
        entity_names: Sequence[str],
    ) -> frozenset[str]:
        return frozenset(
            name
            for name in entity_names
            if name and self._memory_mentions_entity(memory, name)
        )

    @staticmethod
    def _ensure_required_evidence(
        pool: Sequence[RetrievalResult],
        results: Sequence[RetrievalResult],
        required_ids: Sequence[str],
    ) -> list[RetrievalResult]:
        selected = list(pool)
        selected_ids = {result.evidence_id for result in selected}
        protected_ids: set[str] = set()
        for required_id in required_ids:
            identifier = str(required_id)
            if identifier in selected_ids:
                protected_ids.add(identifier)
                continue
            candidate = next(
                (result for result in results if result.evidence_id == identifier),
                None,
            )
            if candidate is None:
                continue
            if selected and len(selected) >= len(pool):
                replace_index = next(
                    (
                        index
                        for index in range(len(selected) - 1, -1, -1)
                        if selected[index].evidence_id not in protected_ids
                    ),
                    None,
                )
                if replace_index is None:
                    continue
                selected_ids.remove(selected[replace_index].evidence_id)
                selected[replace_index] = candidate
            else:
                selected.append(candidate)
            selected_ids.add(identifier)
            protected_ids.add(identifier)
        return selected

    async def _dense_candidates(
        self,
        query: RetrievalQuery,
        query_embedding: list[float] | None,
        *,
        limit: int,
    ) -> tuple[list[MemoryRecord], list[MemoryRecord] | None]:
        if query_embedding is not None:
            vector_search = getattr(self._memories, "get_by_vector_similarity", None)
            if callable(vector_search):
                records = await self._call_candidate_method(
                    vector_search,
                    query.user_id,
                    query_embedding,
                    query=query,
                    limit=limit,
                )
                if records:
                    eligible = [
                        memory for memory in records if self._include_memory(query, memory)
                    ]
                    if eligible:
                        return eligible[:limit], None

        fallback = await self._fallback_memories(query, limit=limit)
        if query_embedding is None:
            return [], fallback
        candidates = [
            memory
            for memory in fallback or []
            if self._cosine_similarity(query_embedding, memory.active_embedding) > 0.0
        ]
        candidates.sort(key=self._dense_order_key(query_embedding))
        return candidates[:limit], fallback

    @staticmethod
    def _expanded_lexical_query(query_text: str) -> str:
        variants: list[str] = []
        if re.search(r"\bwent\b", query_text, re.IGNORECASE):
            variants.append("go")
        if re.search(r"\bgo\b", query_text, re.IGNORECASE):
            variants.append("went")
        if re.search(r"\bmom\b", query_text, re.IGNORECASE):
            variants.append("mother")
        if not variants:
            return query_text
        return f"{query_text} OR {' OR '.join(dict.fromkeys(variants))}"

    async def _lexical_candidates(
        self,
        query: RetrievalQuery,
        *,
        limit: int,
        fallback_memories: list[MemoryRecord] | None,
    ) -> tuple[list[MemoryRecord], list[MemoryRecord] | None]:
        lexical_search = getattr(self._memories, "get_by_lexical_similarity", None)
        if callable(lexical_search):
            records = await self._call_candidate_method(
                lexical_search,
                query.user_id,
                self._expanded_lexical_query(query.query_text),
                query=query,
                limit=limit,
            )
            if records:
                candidates = [
                    memory for memory in records if self._include_memory(query, memory)
                ]
                if candidates:
                    return candidates[:limit], None

        if fallback_memories is None:
            fallback_memories = await self._fallback_memories(query, limit=limit)
        ranked = [
            (self._keyword_score(query.query_text, memory), memory)
            for memory in fallback_memories or []
        ]
        candidates = [memory for score, memory in ranked if score > 0.0]
        candidates.sort(key=lambda memory: self._lexical_order_key(query, memory))
        return candidates[:limit], fallback_memories

    async def _fallback_memories(
        self,
        query: RetrievalQuery,
        *,
        limit: int,
    ) -> list[MemoryRecord] | None:
        get_by_user = getattr(self._memories, "get_by_user", None)
        if not callable(get_by_user):
            return None
        records = await self._call_candidate_method(
            get_by_user,
            query.user_id,
            query=query,
            limit=max(limit * 2, 1000),
        )
        if records is None:
            return None
        return [memory for memory in records if self._include_memory(query, memory)]

    async def _call_candidate_method(
        self,
        method: Any,
        *args: Any,
        query: RetrievalQuery,
        limit: int,
    ) -> Sequence[MemoryRecord] | None:
        kwargs: dict[str, Any] = {"limit": limit}
        try:
            parameters = inspect.signature(method).parameters
        except (TypeError, ValueError):
            parameters = {}
        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        filters: dict[str, Any] = {
            "include_archived": query.include_archived,
            "include_cold": query.include_cold,
            "memory_types": [
                memory_type.value for memory_type in (query.memory_types or [])
            ],
            "tags": query.tags or [],
        }
        for name in ("memory_user_id", "agent_id", "project_id", "session_id"):
            value = getattr(query, name, None)
            if value is not None:
                filters[name] = value
        # Push the bitemporal window into SQL so "what was true at T" is answered
        # by the index instead of discarding already-ranked candidates in Python.
        if getattr(query, "as_of", None) is not None:
            filters["as_of"] = query.as_of
        for name, value in filters.items():
            if accepts_kwargs or name in parameters:
                kwargs[name] = value
        records = await self._try_candidate_call(method, args, kwargs)
        if records is not None:
            return records
        return await self._try_candidate_call(method, args, {"limit": limit})

    @staticmethod
    async def _try_candidate_call(
        method: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> list[MemoryRecord] | None:
        with suppress(Exception):
            records = await method(*args, **kwargs)
            if records is not None:
                return list(records)
        return None

    def _dense_order_key(
        self,
        query_embedding: list[float],
    ) -> Callable[[MemoryRecord], tuple[float, int, float, float, uuid.UUID]]:
        def key(memory: MemoryRecord) -> tuple[float, int, float, float, uuid.UUID]:
            created_at = memory.created_at.timestamp() if memory.created_at else 0.0
            return (
                -self._cosine_similarity(query_embedding, memory.active_embedding),
                int(memory.memory_state == "cold"),
                -float(memory.importance or 0.0),
                -created_at,
                memory.id,
            )

        return key

    def _lexical_order_key(
        self,
        query: RetrievalQuery,
        memory: MemoryRecord,
    ) -> tuple[float, int, float, float, uuid.UUID]:
        created_at = memory.created_at.timestamp() if memory.created_at else 0.0
        return (
            -self._keyword_score(query.query_text, memory),
            int(memory.memory_state == "cold"),
            -float(memory.importance or 0.0),
            -created_at,
            memory.id,
        )

    async def _entity_ids_for_memories(
        self,
        memory_ids: Sequence[uuid.UUID],
    ) -> list[uuid.UUID]:
        if self._links is None or not memory_ids:
            return []
        bulk = getattr(self._links, "bulk_get_entities_for_memories", None)
        if callable(bulk):
            with suppress(Exception):
                return list(
                    dict.fromkeys(link.entity_id for link in await bulk(memory_ids))
                )
        get_for_memory = getattr(self._links, "get_entities_for_memory", None)
        if not callable(get_for_memory):
            return []
        links: list[MemoryEntityLink] = []
        for memory_id in memory_ids:
            with suppress(Exception):
                links.extend(await get_for_memory(memory_id))
        return list(dict.fromkeys(link.entity_id for link in links))

    @classmethod
    def _query_named_entities(cls, query_text: str) -> list[str]:
        names: list[str] = []
        for match in re.finditer(r"\b[A-Z][A-Za-z0-9'’\-]*\b", query_text):
            name = match.group(0).casefold()
            if len(name) < 2 or name in cls.ENTITY_STOPWORDS:
                continue
            names.append(name)
        return list(dict.fromkeys(names))

    @classmethod
    def _is_comparative_or_list_query(cls, query_text: str) -> bool:
        words = set(re.findall(r"[a-z]+", query_text.lower()))
        return bool(words.intersection(cls.COMPARATIVE_MARKERS)) or (
            "and" in words and len(cls._query_named_entities(query_text)) >= 2
        )

    @staticmethod
    def _memory_mentions_entity(memory: MemoryRecord, entity_name: str) -> bool:
        searchable = " ".join(
            str(part)
            for part in (
                getattr(memory, "title", ""),
                getattr(memory, "content", ""),
                " ".join(getattr(memory, "tags", None) or []),
                getattr(memory, "structured_data", None) or "",
            )
        ).casefold()
        return (
            re.search(
                rf"(?<!\w){re.escape(entity_name.casefold())}(?!\w)",
                searchable,
            )
            is not None
        )

    def _promote_entity_coverage(
        self,
        query: RetrievalQuery,
        results: Sequence[RetrievalResult],
        *,
        entity_names: Sequence[str],
        query_plan: QueryPlan | None = None,
        result_limit: int | None = None,
    ) -> list[RetrievalResult]:
        unique_results = list(
            {result.memory.id: result for result in results}.values()
        )
        coverage_entities = list(entity_names)
        if query_plan is not None and query_plan.entities:
            coverage_entities = [*query_plan.entities, *coverage_entities]
        coverage_entities = list(dict.fromkeys(name for name in coverage_entities if name))
        required_ids = list(
            dict.fromkeys(
                str(identifier)
                for identifier in (
                    query_plan.required_evidence_ids if query_plan is not None else []
                )
                if identifier is not None
            )
        )
        should_promote = self._is_comparative_or_list_query(query.query_text)
        if query_plan is not None:
            should_promote = should_promote or query_plan.requires_entity_coverage
        coverage_limit = result_limit if result_limit is not None else query.limit
        if coverage_limit <= 0:
            return []
        if not required_ids and (not should_promote or not coverage_entities):
            return unique_results[:coverage_limit]

        final = unique_results[:coverage_limit]
        final_ids = {result.memory.id for result in final}
        promoted_ids: set[object] = {
            result.memory.id
            for result in final
            if result.evidence_id in required_ids
        }

        def promote(candidate: RetrievalResult) -> bool:
            if len(final) < coverage_limit:
                final.append(candidate)
            else:
                replace_index = next(
                    (
                        index
                        for index in range(len(final) - 1, -1, -1)
                        if final[index].memory.id not in promoted_ids
                    ),
                    None,
                )
                if replace_index is None:
                    return False
                final_ids.remove(final[replace_index].memory.id)
                final[replace_index] = candidate
            final_ids.add(candidate.memory.id)
            promoted_ids.add(candidate.memory.id)
            return True

        for required_id in required_ids:
            if any(result.evidence_id == required_id for result in final):
                continue
            candidate = next(
                (result for result in unique_results if result.evidence_id == required_id),
                None,
            )
            if candidate is not None:
                promote(candidate)

        if not should_promote or not coverage_entities:
            return final
        promotion_budget = min(len(coverage_entities), coverage_limit)
        promotions = 0
        for entity_name in coverage_entities:
            if any(
                self._memory_mentions_entity(result.memory, entity_name)
                for result in final
            ):
                continue
            candidate = next(
                (
                    result
                    for result in unique_results
                    if result.memory.id not in final_ids
                    and self._memory_mentions_entity(result.memory, entity_name)
                ),
                None,
            )
            if candidate is None:
                continue
            if not promote(candidate):
                break
            promotions += 1
            if promotions >= promotion_budget:
                break
        return final

    async def _graph_candidates(
        self,
        query: RetrievalQuery,
        graph_memory_weights: dict[uuid.UUID, float],
        *,
        known_memories: Sequence[MemoryRecord],
        limit: int,
    ) -> list[MemoryRecord]:
        memory_map = {memory.id: memory for memory in known_memories}
        ordered_ids = sorted(
            (
                memory_id
                for memory_id, weight in graph_memory_weights.items()
                if weight > 0.0
            ),
            key=lambda memory_id: (-graph_memory_weights[memory_id], memory_id),
        )[:limit]
        missing_ids = [memory_id for memory_id in ordered_ids if memory_id not in memory_map]
        get_many = getattr(self._memories, "get_many_by_ids", None)
        if missing_ids and callable(get_many):
            fetched: list[MemoryRecord] = []
            with suppress(Exception):
                fetched = list(await get_many(missing_ids))
            for memory in fetched:
                if self._include_memory(query, memory):
                    memory_map[memory.id] = memory
            missing_ids = [
                memory_id for memory_id in missing_ids if memory_id not in memory_map
            ]
        if missing_ids:
            fallback = await self._fallback_memories(query, limit=limit)
            for memory in fallback or []:
                if memory.id in missing_ids:
                    memory_map[memory.id] = memory
        candidates = [
            memory_map[memory_id]
            for memory_id in ordered_ids
            if memory_id in memory_map
            and self._include_memory(query, memory_map[memory_id])
        ]
        candidates.sort(
            key=lambda memory: (-graph_memory_weights[memory.id], memory.id)
        )
        return candidates

    def _channel_weights(
        self,
        cortex_decision: CortexReadDecision | None,
    ) -> dict[str, float]:
        weights = dict(self.DEFAULT_CHANNEL_WEIGHTS)
        if cortex_decision is None:
            return weights
        settings = None
        with suppress(Exception):
            settings = get_settings()
        if settings is None:
            return weights
        if cortex_decision.strategy == "exact":
            weights["lexical"] *= float(
                getattr(settings, "cortex_exact_keyword_boost", 1.5)
            )
        elif cortex_decision.strategy == "semantic":
            weights["dense"] *= float(
                getattr(settings, "cortex_semantic_vector_boost", 1.4)
            )
        elif cortex_decision.strategy == "graph" or cortex_decision.requires_graph:
            weights["graph"] *= float(getattr(settings, "cortex_graph_boost", 1.3))
        return weights

    async def _touch_accessed(self, results: list[RetrievalResult], now: datetime) -> None:
        """Best-effort update of last_accessed_at so decay uses read-age, not write-age."""
        if not results:
            return
        accessed_at = now.replace(tzinfo=None)
        memory_ids = [result.memory.id for result in results]
        touch_many = getattr(self._memories, "touch_accessed_many", None)
        if callable(touch_many):
            with suppress(Exception):
                await touch_many(memory_ids, accessed_at)
                return
        touch = getattr(self._memories, "touch_accessed", None)
        if not callable(touch):
            return
        for memory_id in memory_ids:
            with suppress(Exception):
                await touch(memory_id, accessed_at)

    @staticmethod
    def _scope_uuid(value: Any) -> uuid.UUID | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (AttributeError, TypeError, ValueError):
            return None

    def _include_memory(self, query: RetrievalQuery, memory: MemoryRecord) -> bool:
        requested_user_id = self._scope_uuid(getattr(query, "user_id", None))
        actual_user_id = self._scope_uuid(getattr(memory, "user_id", None))
        if requested_user_id is None or actual_user_id != requested_user_id:
            return False
        requested_organization_id = self._scope_uuid(
            getattr(query, "organization_id", None)
        )
        actual_organization_id = self._scope_uuid(
            getattr(memory, "organization_id", None)
        )
        if (
            requested_organization_id is None
            or actual_organization_id != requested_organization_id
        ):
            return False
        for scope_field in ("memory_user_id", "agent_id", "project_id", "session_id"):
            raw_requested = getattr(query, scope_field, None)
            if raw_requested is None:
                continue
            requested = self._scope_uuid(raw_requested)
            actual = self._scope_uuid(getattr(memory, scope_field, None))
            if requested is None or actual != requested:
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

    def _temporal_expression_matches(self, content: str, expression: str) -> bool:
        normalized_expression = " ".join(expression.casefold().split())
        if normalized_expression in content:
            return True
        expected = self._temporal_date_parts(normalized_expression)
        actual = self._temporal_date_parts(content)
        if expected is None or actual is None:
            return False
        return all(
            expected_value is None or expected_value == actual_value
            for expected_value, actual_value in zip(expected, actual)
        )

    def _temporal_date_parts(
        self,
        text: str,
    ) -> tuple[int | None, int | None, int | None] | None:
        month_pattern = "|".join(self.MONTH_NAMES)
        patterns = (
            (
                r"\b(?P<year>(?:19|20)\d{2})[-/](?P<month>\d{1,2})[-/](?P<day>\d{1,2})\b",
                ("year", "month", "day"),
            ),
            (
                r"\b(?P<month>\d{1,2})[-/](?P<day>\d{1,2})[-/](?P<year>(?:19|20)\d{2})\b",
                ("year", "month", "day"),
            ),
            (
                rf"\b(?P<month>{month_pattern})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<year>(?:19|20)\d{{2}}))?\b",
                ("year", "month", "day"),
            ),
            (
                rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{month_pattern})(?:,?\s+(?P<year>(?:19|20)\d{{2}}))?\b",
                ("year", "month", "day"),
            ),
            (
                rf"\b(?P<month>{month_pattern})\s+(?P<year>(?:19|20)\d{{2}})\b",
                ("year", "month", "day"),
            ),
        )
        for pattern, order in patterns:
            match = re.search(pattern, text)
            if match is None:
                continue
            groups = match.groupdict()
            month_value = groups.get("month")
            if month_value is not None and not month_value.isdigit():
                month_value = str(self.MONTH_NAMES.index(month_value) + 1)
            values = {
                key: int(month_value)
                if key == "month" and month_value is not None
                else int(groups[key])
                if key != "month" and groups.get(key) is not None
                else None
                for key in ("year", "month", "day")
            }
            month = values["month"]
            day = values["day"]
            if month is not None and not 1 <= month <= 12:
                continue
            if day is not None and not 1 <= day <= 31:
                continue
            return tuple(values[key] for key in order)
        return None

    def _temporal_relevance(
        self,
        query: RetrievalQuery,
        memory: MemoryRecord,
        now: datetime,
        *,
        query_plan: QueryPlan | None = None,
    ) -> float:
        text = " ".join(query.query_text.casefold().split())
        plan = query_plan or build_query_plan(query.query_text, now=now)
        explicit_constraints = [
            constraint for constraint in plan.temporal_constraints if constraint.explicit
        ]
        event_at = getattr(memory, "event_at", None)
        if event_at is not None and not isinstance(event_at, datetime):
            event_at = None
        normalized_event = None
        if event_at is not None:
            normalized_event = (
                event_at if event_at.tzinfo is not None else event_at.replace(tzinfo=UTC)
            )
        structured = getattr(memory, "structured_data", None)
        if not isinstance(structured, dict):
            structured = {}
        content = " ".join(
            str(item)
            for item in (getattr(memory, "title", ""), getattr(memory, "content", ""), structured)
            if item
        ).casefold()

        if explicit_constraints:
            matches: list[bool] = []
            for constraint in explicit_constraints:
                start = constraint.start
                end = constraint.end
                if start is not None and start.tzinfo is None:
                    start = start.replace(tzinfo=UTC)
                if end is not None and end.tzinfo is None:
                    end = end.replace(tzinfo=UTC)
                if normalized_event is not None:
                    matches.append(
                        (start is None or normalized_event >= start)
                        and (end is None or normalized_event < end)
                    )
                else:
                    matches.append(
                        self._temporal_expression_matches(
                            content,
                            constraint.expression,
                        )
                        or (start is None and end is None)
                    )
            if not matches or not all(matches):
                return 0.0
            if normalized_event is not None:
                return 1.0 if any(constraint.end is None or constraint.day is not None for constraint in explicit_constraints) else 0.8
            return 0.75

        temporal_query = plan.intent.value == "temporal" or bool(
            re.search(
                r"\b(?:when|what\s+date|how\s+long|yesterday|last\s+year|last\s+week|which\s+year|what\s+year|beginning\s+of)\b",
                text,
            )
        )
        if not temporal_query:
            return 0.0
        expressions = structured.get("temporal_expressions")
        if expressions:
            return 0.75
        if normalized_event is None:
            return 0.0
        if query.temporal_mode in {"current", "as_of", "auto"}:
            # Precision-aware, so a fact stated for a whole year is not held to
            # the standard of an instant timestamp. An `exact`/unresolved-basis
            # row reproduces the previous flat 10-year half-life exactly.
            return max(
                0.0,
                0.65
                * self._freshness(
                    normalized_event,
                    now=now,
                    memory=memory,
                    base_half_life_days=self.TEMPORAL_HALF_LIFE_DAYS,
                ),
            )
        return 0.0

    def _freshness(
        self,
        event_at: datetime,
        *,
        now: datetime,
        memory: MemoryRecord,
        base_half_life_days: float,
    ) -> float:
        """Decay from `event_at` on the half-life `memory`'s precision earns.

        Reads `temporal_precision` and `temporal_basis`, which this retrieval
        path had never read before. `temporal_basis` is the guard: a coarse
        precision label on an unresolved basis is not evidence, so it does not
        relax the half-life. Routed through the injected scoring engine so a
        caller can still own the curve; anything without the method falls back
        to the module-level implementation.
        """
        precision = getattr(memory, "temporal_precision", None)
        basis = getattr(memory, "temporal_basis", None)
        engine = getattr(self._scoring, "compute_precision_aware_freshness", None)
        if callable(engine):
            return float(
                engine(
                    event_at,
                    now=now,
                    temporal_precision=precision,
                    temporal_basis=basis,
                    base_half_life_days=base_half_life_days,
                )
            )
        return compute_precision_aware_freshness(
            event_at,
            now=now,
            temporal_precision=precision,
            temporal_basis=basis,
            base_half_life_days=base_half_life_days,
        )

    def _score_memory(
        self,
        query: RetrievalQuery,
        memory: MemoryRecord,
        *,
        query_embedding: list[float] | None,
        graph_memory_weights: dict[uuid.UUID, float],
        now: datetime,
        cortex_decision: CortexReadDecision | None = None,
        query_plan: QueryPlan | None = None,
    ) -> RetrievalResult:
        semantic = float(self._cosine_similarity(query_embedding, memory.active_embedding))
        graph = float(graph_memory_weights.get(memory.id, 0.0))
        importance = float(max(0.0, min(1.0, memory.importance)))
        event_at = getattr(memory, "event_at", None) or memory.created_at
        # Same 30-day base half-life the scoring engine uses, stretched by the
        # precision of the claim. `exact`/unresolved rows are unchanged; a
        # `year`-precision fact decays 6x slower, so an age gap stops being
        # read as supersession for a claim that never pinned an instant. The
        # contribution stays bounded by w_rec below.
        recency = float(
            self._freshness(
                event_at,
                now=now,
                memory=memory,
                base_half_life_days=self.RECENCY_HALF_LIFE_DAYS,
            )
        )
        keyword = float(self._keyword_score(query.query_text, memory))
        utility = float(max(-1.0, min(1.0, memory.utility_score or 0.0)))
        confidence = float(max(0.0, min(1.0, memory.confidence or 0.0)))
        temporal = self._temporal_relevance(query, memory, now, query_plan=query_plan)

        # Universal conversational speaker context boost:
        # Dynamically matches extracted speaker names from transcripts (e.g. "[Speaker]:" or "Speaker:")
        speaker_bonus = 0.0
        q_lower = query.query_text.lower()
        m_strip = memory.content.strip()
        m_content = m_strip.lower()
        speaker_match = re.match(r"^(?:\[([A-Za-z0-9_-]+)(?:\s+on\s+[^\]]+)?\]|([A-Za-z0-9_-]+):)", m_strip)
        if speaker_match:
            speaker_name = (speaker_match.group(1) or speaker_match.group(2)).lower()
            if (
                speaker_name
                and len(speaker_name) > 1
                and speaker_name not in {"user", "assistant", "system"}
                and re.search(
                    r"\b" + re.escape(speaker_name) + r"(?:'s)?\b",
                    q_lower,
                )
            ):
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
        graph_depth = max(query.graph_depth, query_plan.graph_depth if query_plan is not None else 0)
        if graph_depth >= 2 and graph > 0.0:
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

        # Apply configurable Cortex routing adjustments if decision is present
        type_bonus = 0.0
        if cortex_decision is not None:
            settings = None
            with suppress(Exception):
                settings = get_settings()
            boost_kw = getattr(settings, "cortex_exact_keyword_boost", 1.5) if settings is not None else 1.5
            boost_sem = getattr(settings, "cortex_semantic_vector_boost", 1.4) if settings is not None else 1.4
            boost_graph = getattr(settings, "cortex_graph_boost", 1.3) if settings is not None else 1.3
            boost_temp = getattr(settings, "cortex_temporal_boost", 1.3) if settings is not None else 1.3

            if cortex_decision.strategy == "exact":
                w_kw *= boost_kw
            elif cortex_decision.strategy == "semantic":
                w_sem *= boost_sem
            elif cortex_decision.strategy == "graph" or cortex_decision.requires_graph:
                w_graph *= boost_graph
            elif cortex_decision.strategy == "temporal" or cortex_decision.requires_temporal_filter:
                w_rec *= boost_temp

            if cortex_decision.priority_memory_type and memory.memory_type == cortex_decision.priority_memory_type:
                type_bonus = 0.10

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
            + type_bonus
            + temporal * 0.12
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
            query_plan=query_plan,
        )

    async def _graph_memory_weights(
        self,
        seed_entity_ids: Sequence[uuid.UUID],
        *,
        max_depth: int,
    ) -> dict[uuid.UUID, float]:
        if self._links is None:
            return {}

        hop_distances = await self._entity_hop_distances(
            seed_entity_ids,
            max_depth=max_depth,
        )
        memory_weights: dict[uuid.UUID, float] = {}
        for entity_id, depth in hop_distances.items():
            links = await self._links.get_memories_for_entity(entity_id)
            degree = len(links)
            if degree == 0:
                continue
            # Inverse degree specificity: high-degree hub nodes get lower weight
            weight = (1.0 / (degree ** 0.5)) * (1.0 if depth == 0 else 0.5 ** depth)
            for link in links:
                memory_weights[link.memory_id] = max(
                    memory_weights.get(link.memory_id, 0.0),
                    weight,
                )

        return memory_weights

    async def _entity_hop_distances(
        self,
        seed_entity_ids: Sequence[uuid.UUID],
        *,
        max_depth: int,
    ) -> dict[uuid.UUID, int]:
        """One `walk_entity_graph` round trip for the whole frontier.

        Falls back to the seeds themselves (all at distance 0) when the edge
        repository cannot walk. That is strictly less expansion than the old
        BFS gave, not more, so it can only lower a graph weight; every caller
        in this repo passes a real `EntityEdgeRepository`.
        """
        seeds = list(dict.fromkeys(seed_entity_ids))
        if self._edges is None or not seeds:
            return {entity_id: 0 for entity_id in seeds}
        walk = getattr(self._edges, "walk_entity_graph", None)
        if not callable(walk):
            return {entity_id: 0 for entity_id in seeds}
        distances: dict[uuid.UUID, int] = {}
        with suppress(Exception):
            walked = await walk(seed_entity_ids=seeds, max_depth=max(max_depth, 0))
            distances = {
                entity_id: int(depth)
                for entity_id, depth in (walked or {}).items()
            }
        if not distances:
            return {entity_id: 0 for entity_id in seeds}
        return distances

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
            "went": "go", "mom": "mother", "mother": "mother",
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

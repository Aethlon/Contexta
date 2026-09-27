from __future__ import annotations

import heapq
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from contexta.core.retrieval.query_understanding import QueryPlan
from contexta.models.memory import MemoryRecord

DEFAULT_RRF_K = 60
DEFAULT_UTILITY_PRIOR = 0.005

# A fused candidate score below this is tail noise from the channels, not an
# answer. RRF normalises against the *best possible* rank, so a top-1 hit lands
# near 1.0 and a rank-10 hit near 0.87; the crossover where a single channel
# stops carrying the answer is around rank 60, which scores ~0.45 after the
# engine's 0.80/0.20 blend. Tunable, and meant to be measured before it is
# relied on -- see `RetrievalEngine(enable_dense_escalation=...)`.
DEFAULT_SUFFICIENCY_QUALITY_FLOOR = 0.45

# How far the leader must clear the runner-up to count as "the" answer. A
# single dominant hit is sufficient on its own; a field of near-equals is not,
# however many of them there are.
DEFAULT_SUFFICIENCY_DOMINANCE_MARGIN = 0.10


@dataclass(frozen=True)
class FusedCandidate:
    memory: MemoryRecord
    score: float
    channel_ranks: tuple[tuple[str, int], ...]


def _memory_id(memory: Any) -> Any:
    return getattr(memory, "id", memory)


def weighted_reciprocal_rank_fusion(
    channels: Mapping[str, Sequence[MemoryRecord]],
    *,
    weights: Mapping[str, float],
    rrf_k: int = DEFAULT_RRF_K,
    utility_prior: float = DEFAULT_UTILITY_PRIOR,
    quality_prior: float = 0.0,
) -> list[FusedCandidate]:
    if rrf_k < 1:
        raise ValueError("rrf_k must be at least 1")

    scores: dict[Any, float] = {}
    memories: dict[Any, MemoryRecord] = {}
    ranks: dict[Any, list[tuple[str, int]]] = {}
    active_weight = 0.0

    for channel, candidates in channels.items():
        channel_weight = max(0.0, float(weights.get(channel, 0.0)))
        if channel_weight == 0.0 or not candidates:
            continue
        active_weight += channel_weight
        seen: set[Any] = set()
        rank = 0
        for memory in candidates:
            memory_id = _memory_id(memory)
            if memory_id in seen:
                continue
            seen.add(memory_id)
            rank += 1
            memories[memory_id] = memory
            scores[memory_id] = scores.get(memory_id, 0.0) + channel_weight / (
                rrf_k + rank
            )
            ranks.setdefault(memory_id, []).append((channel, rank))

    if active_weight == 0.0:
        return []

    maximum = active_weight / (rrf_k + 1)
    fused = [
        FusedCandidate(
            memory=memory,
            score=min(
                1.0,
                scores[memory_id] / maximum
                + max(0.0, utility_prior)
                * (
                    (max(-1.0, min(1.0, getattr(memory, "utility_score", 0.0) or 0.0)) + 1.0)
                    / 2.0
                )
                + max(0.0, quality_prior)
                * (
                    0.6 * max(0.0, min(1.0, getattr(memory, "importance", 0.0) or 0.0))
                    + 0.4 * max(0.0, min(1.0, getattr(memory, "confidence", 0.0) or 0.0))
                ),
            ),
            channel_ranks=tuple(ranks[memory_id]),
        )
        for memory_id, memory in memories.items()
    ]
    fused.sort(
        key=lambda candidate: (
            -candidate.score,
            _memory_id(candidate.memory)
            if isinstance(_memory_id(candidate.memory), (UUID, int, float, str))
            else str(_memory_id(candidate.memory)),
        )
    )
    return fused


reciprocal_rank_fusion = weighted_reciprocal_rank_fusion
weighted_rrf = weighted_reciprocal_rank_fusion


@dataclass(frozen=True)
class SufficiencyAssessment:
    """Why the primary channels were or were not enough to answer the plan.

    `reason` is a stable machine-readable token, not a message, so a caller can
    count escalations by cause without parsing prose.
    """

    sufficient: bool
    reason: str
    result_count: int
    required_result_count: int
    covered_entities: tuple[str, ...] = ()
    required_entities: tuple[str, ...] = ()
    missing_evidence_ids: tuple[str, ...] = ()
    top_score: float = 0.0
    runner_up_score: float = 0.0
    margin: float = 0.0


def assess_primary_sufficiency(
    *,
    results: Sequence[Any],
    plan: QueryPlan | None = None,
    required_entity_names: Sequence[str] = (),
    required_evidence_ids: Sequence[str] = (),
    quality_floor: float = DEFAULT_SUFFICIENCY_QUALITY_FLOOR,
    dominance_margin: float = DEFAULT_SUFFICIENCY_DOMINANCE_MARGIN,
) -> SufficiencyAssessment:
    """Decide whether the lexical + graph channels already answered the plan.

    Pure: reads only its arguments, mutates nothing, touches no clock, no
    database and no embedding service, and returns the same assessment for the
    same input. Every threshold is a parameter with a module-level default, so
    it is unit-testable in isolation and tunable without touching the engine.

    The thresholds come from the QueryPlan rather than from a single magic score,
    because "enough" is a property of the *question*, not of the ranker:

    1. **Contract.** Every id the plan named as required evidence, and every
       entity the plan says it must cover, has to be present. This is binary and
       always evaluated first: a plan that names evidence and did not get it is
       never sufficient, however high the top score is.
    2. **Quality.** The leader has to clear `quality_floor`. Several mediocre
       hits are not an answer at any depth, so this gates the depth test too.
    3. **Depth OR dominance.** Past the floor, the primary channels are
       sufficient if they returned at least `plan.retrieval_limit_hint` results
       -- the plan's own statement of how many rows its answer shape needs (a
       table needs 8, a list 6, a one-line fact 3), floored at
       `plan.required_evidence_count` -- or if one hit clears
       `dominance_margin` over everything else. A single strong hit answers a
       one-line question outright; a shallow field of near-equals does not, and
       escalates.
    """
    # Only the top two rows are ever read, and the candidate pool is two orders
    # of magnitude larger than the page, so select rather than sort.
    leaders = heapq.nlargest(
        2,
        results,
        key=lambda result: float(getattr(result, "score", 0.0) or 0.0),
    )
    top_score = float(getattr(leaders[0], "score", 0.0) or 0.0) if leaders else 0.0
    runner_up_score = (
        float(getattr(leaders[1], "score", 0.0) or 0.0) if len(leaders) > 1 else 0.0
    )
    margin = top_score - runner_up_score

    required_result_count = 1
    if plan is not None:
        required_result_count = max(
            1,
            int(plan.retrieval_limit_hint),
            int(plan.required_evidence_count),
        )

    def names(values: Sequence[str]) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                str(item).casefold()
                for item in values
                if item is not None and str(item).strip()
            )
        )

    required_entities = names(
        [
            *(plan.entities if plan is not None else ()),
            *required_entity_names,
        ]
    )
    required_ids = names(
        [
            *(plan.required_evidence_ids if plan is not None else ()),
            *required_evidence_ids,
        ]
    )

    covered: set[str] = set()
    present_ids: set[str] = set()
    for result in results:
        memory = getattr(result, "memory", None)
        if memory is None:
            continue
        identifier = getattr(memory, "id", None)
        if identifier is not None:
            present_ids.add(str(identifier))
        mentions = getattr(result, "mentioned_entities", None) or ()
        covered.update(str(item).casefold() for item in mentions)

    missing_evidence_ids = tuple(item for item in required_ids if item not in present_ids)
    missing_entities = tuple(item for item in required_entities if item not in covered)

    def verdict(sufficient: bool, reason: str) -> SufficiencyAssessment:
        return SufficiencyAssessment(
            sufficient=sufficient,
            reason=reason,
            result_count=len(results),
            required_result_count=required_result_count,
            covered_entities=tuple(
                item for item in required_entities if item in covered
            ),
            required_entities=required_entities,
            missing_evidence_ids=missing_evidence_ids,
            top_score=top_score,
            runner_up_score=runner_up_score,
            margin=margin,
        )

    if missing_evidence_ids:
        return verdict(False, "missing_required_evidence")
    if missing_entities:
        return verdict(False, "missing_required_entity")
    if top_score < quality_floor:
        return verdict(False, "below_quality_floor")
    if len(results) >= required_result_count:
        return verdict(True, "sufficient_depth")
    if margin >= dominance_margin:
        return verdict(True, "sufficient_dominant_hit")
    return verdict(False, "no_dominant_hit")


__all__ = [
    "DEFAULT_RRF_K",
    "DEFAULT_SUFFICIENCY_DOMINANCE_MARGIN",
    "DEFAULT_SUFFICIENCY_QUALITY_FLOOR",
    "DEFAULT_UTILITY_PRIOR",
    "FusedCandidate",
    "SufficiencyAssessment",
    "assess_primary_sufficiency",
    "reciprocal_rank_fusion",
    "weighted_reciprocal_rank_fusion",
    "weighted_rrf",
]

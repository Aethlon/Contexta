"""Regression coverage for the fusion score clamp.

`weighted_reciprocal_rank_fusion` used to clamp the *sum* of the normalised RRF
term and the additive priors to 1.0. The priors are worth ~0.145 at production
settings, so every candidate whose rank-plus-priors crossed 1.0 -- ranks 1 to 11
in all channels -- was frozen onto an identical score, and the top of every
result page was ordered by the engine's 0.20 blend term alone.

The clamp now applies to the normalised RRF term only. Scores may exceed 1.0
inside fusion because the caller (`RetrievalEngine._score_candidates`) owns the
outer `min(1.0, max(0.0, ...))` on the blended result.
"""

import math
from datetime import UTC, datetime
from itertools import pairwise
from uuid import uuid4

from pytest import approx

from contexta.core.retrieval.fusion import (
    DEFAULT_RRF_K,
    DEFAULT_UTILITY_PRIOR,
    weighted_reciprocal_rank_fusion,
)
from contexta.models.memory import MemoryRecord

# Production values from RetrievalEngine: dense 0.5 / lexical 0.3 / graph 0.2
# and FUSION_QUALITY_PRIOR 0.20. Hard-coded on purpose: these are the numbers
# the clamp bug needed to reproduce.
WEIGHTS = {"dense": 0.5, "lexical": 0.3, "graph": 0.2}
QUALITY_PRIOR = 0.20

NEUTRAL_UTILITY = 0.0
NEUTRAL_IMPORTANCE = 0.5167
NEUTRAL_CONFIDENCE = 1.0

# The prior a memory with the neutral attributes above receives. Candidates in
# this file share those attributes, so the prior is a constant offset and the
# ranking is decided by rank alone.
NEUTRAL_PRIOR = (
    DEFAULT_UTILITY_PRIOR * ((NEUTRAL_UTILITY + 1.0) / 2.0)
    + QUALITY_PRIOR * (0.6 * NEUTRAL_IMPORTANCE + 0.4 * NEUTRAL_CONFIDENCE)
)
MAX_PRIOR = DEFAULT_UTILITY_PRIOR + QUALITY_PRIOR


def make_memory(
    *,
    utility_score: float = NEUTRAL_UTILITY,
    importance: float = NEUTRAL_IMPORTANCE,
    confidence: float = NEUTRAL_CONFIDENCE,
) -> MemoryRecord:
    return MemoryRecord(
        id=uuid4(),
        user_id=uuid4(),
        organization_id=uuid4(),
        memory_type="project",
        title="Contexta",
        content="Python retrieval",
        source_type="user_explicit",
        confidence=confidence,
        importance=importance,
        utility_score=utility_score,
        embedding=[1.0, 0.0],
        memory_state="active",
        is_archived=False,
        valid_to=None,
        created_at=datetime.now(UTC),
    )


def fuse(
    channels: dict[str, list[MemoryRecord]],
    *,
    utility_prior: float = DEFAULT_UTILITY_PRIOR,
    quality_prior: float = QUALITY_PRIOR,
) -> dict[object, object]:
    fused = weighted_reciprocal_rank_fusion(
        channels,
        weights=WEIGHTS,
        utility_prior=utility_prior,
        quality_prior=quality_prior,
    )
    return {candidate.memory.id: candidate for candidate in fused}


def scores_at_ranks(pool: list[MemoryRecord], ranks: tuple[int, ...]) -> list[float]:
    """Score each row of `pool` seen at that rank in every channel."""
    by_id = fuse({channel: list(pool) for channel in WEIGHTS})
    return [by_id[pool[rank - 1].id].score for rank in ranks]


def test_production_priors_reproduce_the_frozen_band() -> None:
    # The window the old clamp flattened: any candidate whose normalised RRF
    # term plus this offset crossed 1.0 scored exactly 1.0.
    assert NEUTRAL_PRIOR == approx(0.144504, abs=1e-9)
    assert 1.0 - NEUTRAL_PRIOR == approx(0.855496, abs=1e-9)


def test_ranks_one_five_and_eleven_score_strictly_decreasing() -> None:
    # Before the fix all three were exactly 1.0.
    scores = scores_at_ranks([make_memory() for _ in range(12)], (1, 5, 11))

    assert scores[0] > scores[1] > scores[2]
    assert len(set(scores)) == 3


def test_rank_twelve_scores_below_rank_eleven() -> None:
    scores = scores_at_ranks([make_memory() for _ in range(12)], (11, 12))

    assert scores[1] < scores[0]


def test_rank_order_is_monotonic_across_the_whole_head() -> None:
    # The freeze covered the top ~11 candidates, so check that whole window
    # rather than three isolated ranks.
    scores = scores_at_ranks([make_memory() for _ in range(20)], tuple(range(1, 21)))

    assert all(earlier > later for earlier, later in pairwise(scores))
    assert scores[0] == approx(1.0 + NEUTRAL_PRIOR)
    assert scores[-1] == approx(61.0 / (DEFAULT_RRF_K + 20) + NEUTRAL_PRIOR)


def test_pathological_priors_stay_inside_the_caller_owned_bound() -> None:
    # utility_score, importance and confidence are each clamped into range, so a
    # hostile row contributes at most utility_prior + quality_prior on top of the
    # clamped RRF term -- bounded, not runaway. The bound itself is the caller's:
    # engine.py `_score_candidates` applies min(1.0, max(0.0, ...)).
    hostile = make_memory(utility_score=1e9, importance=1e9, confidence=1e9)
    neutral = make_memory()

    # Both are fused alone at rank 1 in every channel, so the RRF term is
    # identical and only the priors differ.
    hostile_score = fuse({channel: [hostile] for channel in WEIGHTS})[hostile.id].score
    neutral_score = fuse({channel: [neutral] for channel in WEIGHTS})[neutral.id].score

    # The hostile row's priors are clamped to their maxima, not allowed to scale
    # without bound.
    assert hostile_score - neutral_score == approx(MAX_PRIOR - NEUTRAL_PRIOR)
    assert hostile_score <= 1.0 + MAX_PRIOR

    # Applied the way the engine applies it, the observable score saturates at
    # the bound rather than escaping it.
    assert min(1.0, max(0.0, hostile_score)) == 1.0


def test_out_of_range_priors_cannot_go_negative_or_produce_nan() -> None:
    nan = float("nan")
    pool = [
        make_memory(utility_score=nan, importance=nan, confidence=nan),
        make_memory(utility_score=-1.0, importance=0.0, confidence=0.0),
        make_memory(utility_score=1.0, importance=1.0, confidence=1.0),
    ]

    # Negative priors are discarded by max(0.0, prior), leaving pure RRF.
    by_id = fuse(
        {channel: list(pool) for channel in WEIGHTS},
        utility_prior=-5.0,
        quality_prior=-5.0,
    )

    assert [by_id[memory.id].score for memory in pool] == approx(
        [61.0 / (DEFAULT_RRF_K + rank) for rank in (1, 2, 3)]
    )

    # NaN priors are discarded by the same guard rather than propagated.
    by_id_with_nan_priors = fuse(
        {channel: list(pool) for channel in WEIGHTS},
        utility_prior=nan,
        quality_prior=nan,
    )

    for rank, memory in enumerate(pool, start=1):
        score = by_id_with_nan_priors[memory.id].score
        assert score == approx(61.0 / (DEFAULT_RRF_K + rank))
        assert score >= 0.0
        assert not math.isnan(score)


def test_single_channel_candidate_ranks_below_the_same_candidate_in_all_three() -> None:
    everywhere = make_memory()
    dense_only = make_memory()

    by_id = fuse(
        {
            "dense": [everywhere, dense_only],
            "lexical": [everywhere, make_memory()],
            "graph": [everywhere, make_memory()],
        }
    )

    assert len(by_id[everywhere.id].channel_ranks) == 3
    assert len(by_id[dense_only.id].channel_ranks) == 1
    assert by_id[everywhere.id].score > by_id[dense_only.id].score


def test_single_channel_is_not_inflated_against_a_multi_channel_candidate() -> None:
    # Best case for the single-channel candidate, worst case for the
    # multi-channel one: maximal priors on one, no priors on the other. The
    # ordering property, not an exact number.
    loud_single = make_memory(utility_score=1.0, importance=1.0, confidence=1.0)
    quiet_everywhere = make_memory(utility_score=-1.0, importance=0.0, confidence=0.0)

    # Separate fusions, because a rank-1 slot is unique per channel: the
    # single-channel candidate is dense rank 1 here, and rank 1 in all three
    # channels in the other.
    single_only = fuse(
        {
            "dense": [loud_single],
            "lexical": [make_memory()],
            "graph": [make_memory()],
        }
    )
    in_all_three = fuse(
        {channel: [quiet_everywhere] for channel in WEIGHTS},
        utility_prior=0.0,
        quality_prior=0.0,
    )

    # dense carries 0.5 of the 1.0 active weight, so a dense-only rank-1 hit
    # normalises to 0.5 and the maximal prior is worth 0.205.
    assert single_only[loud_single.id].score == approx(WEIGHTS["dense"] + MAX_PRIOR)
    assert in_all_three[quiet_everywhere.id].score == approx(1.0)
    assert single_only[loud_single.id].score < in_all_three[quiet_everywhere.id].score


def test_single_channel_at_rank_two_ranks_below_the_same_candidate_in_all_three() -> None:
    loud_single = make_memory(utility_score=1.0, importance=1.0, confidence=1.0)
    quiet_everywhere = make_memory(utility_score=-1.0, importance=0.0, confidence=0.0)

    by_id = fuse(
        {
            "dense": [quiet_everywhere, loud_single],
            "lexical": [quiet_everywhere, make_memory()],
            "graph": [quiet_everywhere, make_memory()],
        }
    )

    # Rank 1 in all three channels normalises to the full 1.0; rank 2 in dense
    # alone is worth the dense weight over its share of the RRF.
    dense_only_rank_2 = WEIGHTS["dense"] * 61.0 / (DEFAULT_RRF_K + 2)
    assert by_id[quiet_everywhere.id].score == approx(1.0)
    assert by_id[loud_single.id].score == approx(dense_only_rank_2 + MAX_PRIOR)
    assert by_id[loud_single.id].score < by_id[quiet_everywhere.id].score


def test_the_prior_is_the_same_additive_offset_for_every_candidate() -> None:
    # Before the fix the clamp absorbed the prior for a strong multi-channel
    # candidate but kept all of it for a weak single-channel one, so the prior
    # was a strictly-inverted bonus. Both now receive the same additive term.
    pool = [make_memory() for _ in range(4)]

    with_priors = fuse({channel: list(pool) for channel in WEIGHTS})
    without_priors = fuse(
        {channel: list(pool) for channel in WEIGHTS},
        utility_prior=0.0,
        quality_prior=0.0,
    )

    for memory in pool:
        assert with_priors[memory.id].score - without_priors[memory.id].score == (
            approx(NEUTRAL_PRIOR)
        )

"""Memory scoring engine."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from contexta.core.schemas import ImportanceSignals
from contexta.core.scoring.importance import ImportanceBreakdown, ImportanceFramework
from contexta.core.types import MemoryType, SourceType

# Granularity ranking, mirroring the canonical ordering in
# `contexta.core.temporal._interval_precision`: an interval's precision is the
# *coarsest* of its endpoints, so coarser statements rank higher because they
# make weaker claims about ordering within the period. temporal.py is the owner
# of that ordering and is not importable from here without a cycle, so this table
# is kept in step with it by hand.
PRECISION_RANK: dict[str, int] = {
    "unknown": 0,
    "second": 1,
    "minute": 1,
    "hour": 1,
    "exact": 2,
    "day": 3,
    "week": 4,
    "month": 5,
    "quarter": 6,
    "year": 7,
}

# The two ends of the ranking above. `exact` and anything finer keeps the
# undilated half-life, so existing instant-precision scoring is bit-for-bit
# unchanged; only coarse statements are relieved.
_EXACT_RANK = PRECISION_RANK["exact"]
_COARSEST_RANK = PRECISION_RANK["year"]

# How much extra half-life the coarsest granularity (`year`) buys over `exact`.
# A fact stated for a whole year makes no claim about ordering inside it, so a
# large age gap is weak evidence that it was superseded, whereas an
# instant-precision claim of the same age plausibly was. 6x keeps the whole
# effect inside the bounded recency/temporal weights the caller applies.
COARSE_HALF_LIFE_GROWTH = 5.0

# `temporal_basis` values that mean the timestamp was never anchored to a
# resolved expression. A coarse precision label on an unresolved basis is not
# evidence of anything, so it must not be allowed to relax the half-life.
_UNRESOLVED_BASIS_PREFIXES = ("unresolved",)
_UNRESOLVED_BASIS_VALUES = frozenset({"unavailable", "none", "unknown"})


def precision_half_life_scale(
    temporal_precision: str | None,
    temporal_basis: str | None = None,
) -> float:
    """Return the freshness half-life multiplier implied by a claim's precision.

    Linear in the canonical precision rank, anchored so `exact` (and anything
    finer or unknown) is exactly ``1.0`` and `year`` is exactly
    ``1.0 + COARSE_HALF_LIFE_GROWTH``. Pure, and total over unknown inputs.
    """
    basis = str(temporal_basis or "").strip().casefold()
    if basis in _UNRESOLVED_BASIS_VALUES or basis.startswith(
        _UNRESOLVED_BASIS_PREFIXES
    ):
        return 1.0
    precision = str(temporal_precision or "").strip().casefold()
    rank = PRECISION_RANK.get(precision, _EXACT_RANK)
    steps = max(0, rank - _EXACT_RANK)
    span = _COARSEST_RANK - _EXACT_RANK
    if span <= 0:
        return 1.0
    return 1.0 + COARSE_HALF_LIFE_GROWTH * (steps / span)


def compute_precision_aware_freshness(
    occurred_at: datetime,
    *,
    now: datetime | None = None,
    temporal_precision: str | None = None,
    temporal_basis: str | None = None,
    base_half_life_days: float = 3650.0,
) -> float:
    """`compute_freshness` with the half-life scaled by the claim's precision.

    Same curve as `compute_freshness`, so a call with `exact`/unresolved
    precision reproduces it exactly; only a coarse but *resolved* claim decays
    more slowly. `temporal_precision` is the ranking key and `temporal_basis`
    decides whether that key can be trusted at all.
    """
    half_life_days = base_half_life_days * precision_half_life_scale(
        temporal_precision,
        temporal_basis,
    )
    if half_life_days <= 0:
        half_life_days = 30.0
    reference = now or datetime.now(UTC)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    age_days = max((reference - occurred_at).total_seconds(), 0.0) / 86_400
    return math.exp(-math.log(2) * age_days / half_life_days)


class MemoryScoringEngine:
    """Compute importance, confidence, freshness, and utility scores."""

    CONFIDENCE_BY_SOURCE: dict[SourceType, float] = {
        SourceType.USER_EXPLICIT: 1.0,
        SourceType.TOOL_OUTPUT: 0.8,
        SourceType.AGENT_INFERENCE: 0.6,
        SourceType.IMPORTED_FILE: 0.7,
        SourceType.API: 0.7,
    }

    def __init__(self, importance_framework: ImportanceFramework | None = None) -> None:
        self._importance = importance_framework or ImportanceFramework()

    def compute_importance(
        self,
        memory_type: MemoryType,
        content: str,
        signals: ImportanceSignals | None = None,
        *,
        now: datetime | None = None,
    ) -> ImportanceBreakdown:
        """Compute importance by delegating to the importance framework."""
        return self._importance.compute(memory_type, content, signals, now=now)

    def compute_confidence(self, source_type: SourceType) -> float:
        """Return deterministic confidence for a source type."""
        return self.CONFIDENCE_BY_SOURCE[source_type]

    def compute_freshness(
        self,
        created_at: datetime,
        *,
        now: datetime | None = None,
        half_life_days: float = 30.0,
    ) -> float:
        """Compute monotonically decreasing freshness from age."""
        reference = now or datetime.now(UTC)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        age_seconds = max((reference - created_at).total_seconds(), 0.0)
        age_days = age_seconds / 86_400
        if half_life_days <= 0:
            half_life_days = 30.0
        return math.exp(-math.log(2) * age_days / half_life_days)

    def compute_utility(self, usage_count: int, retrieval_count: int) -> float:
        """Compute bounded usage_count / retrieval_count utility ratio."""
        if retrieval_count <= 0:
            return 0.0
        ratio = max(usage_count, 0) / retrieval_count
        return max(0.0, min(1.0, ratio))

    def compute_precision_aware_freshness(
        self,
        occurred_at: datetime,
        *,
        now: datetime | None = None,
        temporal_precision: str | None = None,
        temporal_basis: str | None = None,
        base_half_life_days: float = 3650.0,
    ) -> float:
        """Delegates to `compute_precision_aware_freshness` for the caller's precision."""
        return compute_precision_aware_freshness(
            occurred_at,
            now=now,
            temporal_precision=temporal_precision,
            temporal_basis=temporal_basis,
            base_half_life_days=base_half_life_days,
        )


__all__ = [
    "COARSE_HALF_LIFE_GROWTH",
    "ImportanceBreakdown",
    "ImportanceFramework",
    "MemoryScoringEngine",
    "PRECISION_RANK",
    "compute_precision_aware_freshness",
    "precision_half_life_scale",
]

"""Memory scoring engine."""

from __future__ import annotations

from datetime import datetime, timezone
import math

from contexta.core.schemas import ImportanceSignals
from contexta.core.scoring.importance import ImportanceBreakdown, ImportanceFramework
from contexta.core.types import MemoryType, SourceType


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
        reference = now or datetime.now(timezone.utc)
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

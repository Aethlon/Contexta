"""Importance framework for memory candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re

from contexta.core.schemas import ImportanceSignals
from contexta.core.types import MemoryType


@dataclass(frozen=True)
class ImportanceBreakdown:
    """Importance score plus its component contributions."""

    base_score: float
    repetition: float
    recency: float
    emphasis: float
    decision_impact: float
    utility: float
    final_score: float
    rejected: bool = False
    rejection_reason: str | None = None


class ImportanceFramework:
    """Compute memory importance from type and contextual signals."""

    BASE_SCORES: dict[MemoryType, float] = {
        MemoryType.FACT: 0.45,
        MemoryType.PREFERENCE: 0.65,
        MemoryType.GOAL: 0.75,
        MemoryType.PROJECT: 0.8,
        MemoryType.SKILL: 0.7,
        MemoryType.RELATIONSHIP: 0.6,
        MemoryType.EVENT: 0.5,
        MemoryType.EPISODIC: 0.4,
        MemoryType.PATTERN: 0.6,
        MemoryType.CONTACT: 0.7,
        MemoryType.CUSTOM: 0.5,
    }

    _LOW_VALUE_PATTERNS = [
        re.compile(r"^\s*(hi|hello|hey|yo|sup|thanks|thank you|ok|okay|cool)\s*[!.]*\s*$", re.I),
        re.compile(r"^\s*(how are you|good morning|good afternoon|good evening)\s*[?.!]*\s*$", re.I),
        re.compile(r"^\s*(lol|haha|nice|great|awesome|sounds good)\s*[!.]*\s*$", re.I),
    ]

    def compute(
        self,
        memory_type: MemoryType,
        content: str,
        signals: ImportanceSignals | None = None,
        *,
        now: datetime | None = None,
    ) -> ImportanceBreakdown:
        """Compute importance and reject low-value content."""
        if self.is_low_value(content):
            return ImportanceBreakdown(
                base_score=0.0,
                repetition=0.0,
                recency=0.0,
                emphasis=0.0,
                decision_impact=0.0,
                utility=0.0,
                final_score=0.0,
                rejected=True,
                rejection_reason="low_value_content",
            )

        signals = signals or ImportanceSignals()
        base_score = self.BASE_SCORES[memory_type]
        repetition = self.repetition_modifier(signals.mention_count)
        recency = self.recency_modifier(signals.last_referenced, now=now)
        emphasis = 0.15 if signals.has_emphasis else 0.0
        decision_impact = 0.1 if signals.impacts_decisions else 0.0
        utility = self.utility_modifier(signals.utility_ratio)
        final_score = self._clamp(
            base_score + repetition + recency + emphasis + decision_impact + utility
        )

        return ImportanceBreakdown(
            base_score=base_score,
            repetition=repetition,
            recency=recency,
            emphasis=emphasis,
            decision_impact=decision_impact,
            utility=utility,
            final_score=final_score,
        )

    def is_low_value(self, content: str) -> bool:
        """Return true for greetings, small talk, and filler content."""
        stripped = content.strip()
        if not stripped:
            return True
        return any(pattern.match(stripped) for pattern in self._LOW_VALUE_PATTERNS)

    def repetition_modifier(self, mention_count: int) -> float:
        """Bound repetition modifier to +0.1 at 3+ mentions."""
        return min(max(mention_count, 0), 3) / 3 * 0.1

    def recency_modifier(
        self,
        last_referenced: datetime | None,
        *,
        now: datetime | None = None,
    ) -> float:
        """Return +0.05 for memories referenced within the last 7 days."""
        if last_referenced is None:
            return 0.0
        reference = now or datetime.now(timezone.utc)
        if last_referenced >= reference - timedelta(days=7):
            return 0.05
        return 0.0

    def utility_modifier(self, utility_ratio: float | None) -> float:
        """Map utility ratio to a bounded [-0.1, 0.1] modifier."""
        if utility_ratio is None:
            return 0.0
        return self._clamp((utility_ratio - 0.5) * 0.2, lower=-0.1, upper=0.1)

    def _clamp(
        self,
        value: float,
        *,
        lower: float = 0.0,
        upper: float = 1.0,
    ) -> float:
        return max(lower, min(upper, value))

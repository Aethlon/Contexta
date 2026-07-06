"""Tests for memory scoring engine."""

from datetime import datetime, timedelta, timezone

from contexta.core.schemas import ImportanceSignals
from contexta.core.scoring.engine import MemoryScoringEngine
from contexta.core.types import MemoryType, SourceType


def test_confidence_mapping_is_deterministic() -> None:
    engine = MemoryScoringEngine()

    assert engine.compute_confidence(SourceType.USER_EXPLICIT) == 1.0
    assert engine.compute_confidence(SourceType.TOOL_OUTPUT) == 0.8
    assert engine.compute_confidence(SourceType.AGENT_INFERENCE) == 0.6
    assert engine.compute_confidence(SourceType.IMPORTED_FILE) == 0.7
    assert engine.compute_confidence(SourceType.API) == 0.7


def test_freshness_monotonically_decreases_with_age() -> None:
    engine = MemoryScoringEngine()
    now = datetime.now(timezone.utc)

    fresh = engine.compute_freshness(now - timedelta(days=1), now=now)
    stale = engine.compute_freshness(now - timedelta(days=60), now=now)

    assert 0.0 <= stale <= fresh <= 1.0


def test_utility_ratio_is_bounded() -> None:
    engine = MemoryScoringEngine()

    assert engine.compute_utility(0, 0) == 0.0
    assert engine.compute_utility(3, 6) == 0.5
    assert engine.compute_utility(10, 5) == 1.0
    assert engine.compute_utility(-1, 5) == 0.0


def test_compute_importance_delegates_to_framework() -> None:
    engine = MemoryScoringEngine()

    result = engine.compute_importance(
        MemoryType.GOAL,
        "The user wants to ship the contexta MVP.",
        ImportanceSignals(impacts_decisions=True),
    )

    assert result.base_score == 0.75
    assert result.decision_impact == 0.1

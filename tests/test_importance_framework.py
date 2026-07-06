"""Tests for memory importance scoring."""

from datetime import datetime, timedelta, timezone

from contexta.core.schemas import ImportanceSignals
from contexta.core.scoring.importance import ImportanceFramework
from contexta.core.types import MemoryType


def test_base_score_mapping_covers_all_memory_types() -> None:
    assert set(ImportanceFramework.BASE_SCORES) == set(MemoryType)


def test_importance_score_is_clamped_to_one() -> None:
    framework = ImportanceFramework()
    score = framework.compute(
        MemoryType.PROJECT,
        "Important project decision",
        ImportanceSignals(
            mention_count=100,
            last_referenced=datetime.now(timezone.utc),
            has_emphasis=True,
            impacts_decisions=True,
            utility_ratio=1.0,
        ),
    )

    assert score.final_score == 1.0


def test_modifier_bounds() -> None:
    framework = ImportanceFramework()
    now = datetime.now(timezone.utc)

    assert framework.repetition_modifier(10) == 0.1
    assert framework.recency_modifier(now, now=now) == 0.05
    assert framework.recency_modifier(now - timedelta(days=8), now=now) == 0.0
    assert framework.utility_modifier(0.0) == -0.1
    assert framework.utility_modifier(1.0) == 0.1


def test_low_value_content_is_rejected() -> None:
    framework = ImportanceFramework()
    result = framework.compute(MemoryType.FACT, "hello")

    assert result.rejected is True
    assert result.rejection_reason == "low_value_content"
    assert result.final_score == 0.0


def test_meaningful_content_is_not_rejected() -> None:
    framework = ImportanceFramework()
    result = framework.compute(
        MemoryType.PREFERENCE,
        "The user prefers Python for backend services.",
    )

    assert result.rejected is False
    assert result.final_score == framework.BASE_SCORES[MemoryType.PREFERENCE]

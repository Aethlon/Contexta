import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from contexta.core.extraction.worker import ExtractionWorker
from contexta.core.pipeline import FastMemoryOrchestrator
from contexta.core.schemas import ExtractedMemory, ObservationPayload
from contexta.core.temporal import (
    normalize_temporal_expression,
    normalize_temporal_messages,
    normalize_temporal_text,
)
from contexta.core.types import MemoryType, SourceType


class FakeLLMService:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.prompts: list[str] = []

    async def complete_json(self, prompt: str, system_prompt: str | None = None) -> dict:
        self.prompts.append(prompt)
        return self.response


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("yesterday", "2026-09-06"),
        ("today", "2026-09-07"),
        ("tomorrow", "2026-09-08"),
        ("last week", "2026-08-31 through 2026-09-06"),
        ("this week", "2026-09-07 through 2026-09-13"),
        ("next week", "2026-09-14 through 2026-09-20"),
        ("last month", "2026-08-01 through 2026-08-31"),
        ("this month", "2026-09-01 through 2026-09-30"),
        ("next month", "2026-10-01 through 2026-10-31"),
        ("last year", "2025-01-01 through 2025-12-31"),
        ("this year", "2026-01-01 through 2026-12-31"),
        ("next year", "2027-01-01 through 2027-12-31"),
        ("last Friday", "2026-09-04"),
        ("this Monday", "2026-09-07"),
        ("next Monday", "2026-09-14"),
        ("Monday", "2026-09-07"),
        ("3 days ago", "2026-09-04"),
        ("two days ago", "2026-09-05"),
        ("2 weeks ago", "2026-08-24"),
        ("2 months ago", "2026-07-07"),
        ("1 year ago", "2025-09-07"),
    ],
)
def test_normalize_temporal_expression(expression: str, expected: str) -> None:
    reference = datetime(2026, 9, 7, 12, 30, tzinfo=UTC)
    result = normalize_temporal_expression(expression, reference)

    assert result.original_expression == expression
    assert result.normalized_expression == expected
    assert result.resolved_at is not None
    assert result.resolved_at.tzinfo is not None


def test_normalize_temporal_text_preserves_source_expression() -> None:
    result = normalize_temporal_text(
        "The release happened yesterday and next month.",
        datetime(2026, 9, 7, tzinfo=UTC),
    )

    assert "2026-09-06" in result.normalized_text
    assert "2026-10-01 through 2026-10-31" in result.normalized_text
    assert [match.original_expression for match in result.matches] == ["yesterday", "next month"]


def test_normalize_temporal_text_does_not_invent_relative_dates() -> None:
    result = normalize_temporal_text("The release happened yesterday.")

    assert result.normalized_text == "The release happened yesterday."
    assert result.matches[0].original_expression == "yesterday"
    assert result.matches[0].resolved_at is None


def test_normalize_temporal_text_uses_requested_timezone() -> None:
    result = normalize_temporal_expression(
        "yesterday",
        datetime(2026, 9, 8, 2, 0, tzinfo=UTC),
        timezone="America/Los_Angeles",
    )

    assert result.resolved_at is not None
    assert result.resolved_at.date().isoformat() == "2026-09-06"
    assert result.resolved_at.tzinfo is not None


@pytest.mark.parametrize(
    ("expression", "expected", "precision", "expected_end"),
    [
        ("20 July, 2023", "2023-07-20", "day", None),
        ("May 3, 2023", "2023-05-03", "day", None),
        ("May 2023", "2023-05-01 through 2023-05-31", "month", "2023-05-31"),
        ("in 2010", "2010-01-01 through 2010-12-31", "year", "2010-12-31"),
    ],
)
def test_normalize_temporal_expression_explicit_date_forms(
    expression: str,
    expected: str,
    precision: str,
    expected_end: str | None,
) -> None:
    result = normalize_temporal_expression(expression)

    assert result.normalized_expression == expected
    assert result.temporal_precision == precision
    assert result.temporal_basis == "explicit_date"
    assert result.resolved_at is not None
    if expected_end is None:
        assert result.end_at is None
    else:
        assert result.end_at is not None
        assert result.end_at.date().isoformat() == expected_end


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("week before 2023-07-20", "2023-07-13"),
        ("week before 20 July, 2023", "2023-07-13"),
    ],
)
def test_normalize_temporal_expression_week_before_explicit_date(
    expression: str,
    expected: str,
) -> None:
    result = normalize_temporal_expression(expression)

    assert result.normalized_expression == expected
    assert result.resolved_at is not None
    assert result.temporal_precision == "day"


@pytest.mark.parametrize(
    "expression",
    ["week before May 2023", "week before next month", "03/04/2023"],
)
def test_normalize_temporal_text_keeps_ambiguous_expressions_unresolved(expression: str) -> None:
    reference = datetime(2026, 9, 7, 12, 30, tzinfo=UTC)
    result = normalize_temporal_text(expression, reference)

    assert result.normalized_text == expression
    assert all(match.resolved_at is None for match in result.matches)


def test_normalize_temporal_messages_normalizes_content_and_text() -> None:
    reference = datetime(2026, 9, 7, 12, 30, tzinfo=UTC)
    result = normalize_temporal_messages(
        [{"content": "It happened yesterday.", "text": "The date was May 3, 2023."}],
        occurred_at=reference,
    )

    assert result[0]["content"] == "It happened 2026-09-06."
    assert result[0]["text"] == "The date was 2023-05-03."
    assert [match["original_expression"] for match in result[0]["temporal"]["matches"]] == [
        "yesterday",
        "May 3, 2023",
    ]


def test_extraction_prompt_and_memory_are_temporally_grounded() -> None:
    llm = FakeLLMService(
        {
            "memories": [
                {
                    "memory_type": "event",
                    "source_type": "user_explicit",
                    "title": "Release",
                    "content": "The release happened yesterday.",
                    "structured_data": {},
                }
            ]
        },
    )
    worker = ExtractionWorker(llm_service=llm)
    payload = ObservationPayload(
        user_id=uuid4(),
        organization_id=uuid4(),
        session_id=uuid4(),
        messages=[
            {
                "role": "user",
                "content": "The release happened yesterday.",
                "occurred_at": "2026-09-07T12:00:00+00:00",
                "message_id": "message-1",
            }
        ],
        observed_at="2026-09-07T12:01:00+00:00",
    )

    memories = asyncio.run(worker.extract(payload))

    assert len(memories) == 1
    assert "2026-09-06" in memories[0].content
    assert memories[0].event_at is not None
    assert memories[0].event_at.date().isoformat() == "2026-09-06"
    assert memories[0].temporal_basis == "relative_expression"
    assert "2026-09-06" in llm.prompts[0]
    prompt = json.loads(llm.prompts[0])
    assert "2026-09-06" in prompt["messages"][0]["text"]
    assert prompt["messages"][0]["temporal"]["matches"][0]["original_expression"] == "yesterday"


def test_extraction_without_source_date_keeps_expression_unknown() -> None:
    llm = FakeLLMService(
        {
            "memories": [
                {
                    "memory_type": "event",
                    "source_type": "user_explicit",
                    "title": "Release",
                    "content": "The release happened yesterday.",
                }
            ]
        },
    )
    worker = ExtractionWorker(llm_service=llm)
    payload = ObservationPayload(
        user_id=uuid4(),
        organization_id=uuid4(),
        session_id=uuid4(),
        messages=[{"role": "user", "content": "The release happened yesterday."}],
    )

    memories = asyncio.run(worker.extract(payload))

    assert memories[0].content == "The release happened yesterday."
    assert memories[0].event_at is None
    assert memories[0].temporal_basis == "ingestion_fallback"


def test_pipeline_derives_valid_time_and_marks_unknown_fallback() -> None:
    orchestrator = object.__new__(FastMemoryOrchestrator)
    ingestion_at = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    payload = ObservationPayload(
        user_id=uuid4(),
        organization_id=uuid4(),
        session_id=uuid4(),
        messages=[{"role": "user", "content": "A durable preference."}],
    )
    memory = ExtractedMemory(
        memory_type=MemoryType.PREFERENCE,
        source_type=SourceType.USER_EXPLICIT,
        title="Preference",
        content="A durable preference.",
    )
    normalized_messages = normalize_temporal_messages(payload.messages)

    grounded = orchestrator._ground_memory_temporal(
        memory,
        payload,
        normalized_messages,
        ingestion_at,
    )
    structured = orchestrator._structured_data_for_record(grounded)

    assert grounded.event_at is None
    assert grounded.temporal_basis == "ingestion_fallback"
    assert orchestrator._valid_from_for_record(grounded, ingestion_at) == ingestion_at.replace(tzinfo=None)
    assert structured["temporal"]["event_at"] is None
    assert structured["temporal"]["valid_from_basis"] == "ingestion_fallback"


def test_offline_pipeline_does_not_call_default_cortex() -> None:
    from contexta.config.settings import Settings
    from contexta.core.cortex import ContextaCortex

    settings = Settings(engine_mode="offline")
    settings.engine_mode = "offline"
    cortex = ContextaCortex(settings=settings)
    cortex.evaluate_observation = AsyncMock()
    extractor = type("Extractor", (), {"extract": AsyncMock(return_value=[])})()
    orchestrator = FastMemoryOrchestrator(cortex=cortex, extraction_worker=extractor)
    payload = ObservationPayload(
        user_id=uuid4(),
        organization_id=uuid4(),
        session_id=uuid4(),
        messages=[{"role": "user", "content": "A statement."}],
    )

    with patch("contexta.core.pipeline.get_settings", return_value=settings):
        asyncio.run(orchestrator.orchestrate(payload, AsyncMock()))

    cortex.evaluate_observation.assert_not_awaited()
    extractor.extract.assert_awaited_once()
    assert extractor.extract.await_args.kwargs["cortex_decision"] is None

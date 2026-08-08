"""Tests for LLM-backed extraction worker behavior."""

import pytest

from contexta.core.extraction.worker import ExtractionWorker
from contexta.core.schemas import ObservationPayload
from contexta.core.types import MemoryType, SourceType


class FakeLLMService:
    """Minimal fake LLM service for deterministic extraction tests."""

    def __init__(self, response: dict) -> None:
        self.response = response

    async def complete_json(self, prompt: str, system_prompt: str | None = None) -> dict:
        return self.response


@pytest.fixture
def observation_payload() -> ObservationPayload:
    return ObservationPayload(
        user_id="00000000-0000-0000-0000-000000000001",
        organization_id="00000000-0000-0000-0000-000000000002",
        session_id="00000000-0000-0000-0000-000000000003",
        messages=[{"role": "user", "content": "I prefer Python for backend work."}],
    )


async def test_extract_returns_typed_memories(observation_payload: ObservationPayload) -> None:
    worker = ExtractionWorker(
        llm_service=FakeLLMService(
            {
                "memories": [
                    {
                        "memory_type": "preference",
                        "source_type": "user_explicit",
                        "title": "Prefers Python",
                        "content": "The user prefers Python for backend work.",
                        "tags": ["python", "backend"],
                    }
                ]
            }
        )
    )

    memories = await worker.extract(observation_payload)

    assert len(memories) == 1
    assert memories[0].memory_type == MemoryType.PREFERENCE
    assert memories[0].source_type == SourceType.USER_EXPLICIT
    assert memories[0].title == "Prefers Python"


async def test_extract_applies_defaults(observation_payload: ObservationPayload) -> None:
    worker = ExtractionWorker(
        llm_service=FakeLLMService(
            {
                "memories": [
                    {
                        "content": "The user is working on the contexta project.",
                    }
                ]
            }
        )
    )

    memories = await worker.extract(observation_payload)

    assert len(memories) == 1
    assert memories[0].memory_type == MemoryType.CUSTOM
    assert memories[0].source_type == SourceType.AGENT_INFERENCE
    assert memories[0].title == "The user is working on the contexta project."


async def test_extract_discards_sensitive_memory(
    observation_payload: ObservationPayload,
) -> None:
    worker = ExtractionWorker(
        llm_service=FakeLLMService(
            {
                "memories": [
                    {
                        "memory_type": "fact",
                        "source_type": "user_explicit",
                        "title": "API key",
                        "content": "The API key is sk-abcdefghijklmnopqrstuvwxyz123456.",
                    }
                ]
            }
        )
    )

    assert await worker.extract(observation_payload) == []

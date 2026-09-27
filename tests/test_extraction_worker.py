"""Tests for LLM-backed extraction worker behavior."""

import json

import httpx
import pytest

from contexta.config.settings import Settings
from contexta.core.extraction.worker import ExtractionWorker
from contexta.core.schemas import ObservationPayload
from contexta.core.types import MemoryType, SourceType
from contexta.services.llm import LLMService, infer_memory_type, normalize_memory_type_label


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


async def test_offline_llm_skips_disabled_model_server(monkeypatch) -> None:
    async def unexpected_post(*args, **kwargs):
        raise AssertionError("disabled model server must not be called")

    monkeypatch.setattr(httpx.AsyncClient, "post", unexpected_post)
    settings = Settings(engine_mode="offline", local_model_server_enabled=False)
    response = await LLMService(settings).complete_json(
        json.dumps({"messages": [{"speaker": "User", "text": "I prefer Python."}]})
    )

    assert response["memories"][0]["content"] == "User: I prefer Python."


def test_normalize_classifier_memory_type() -> None:
    assert normalize_memory_type_label("other") == "custom"
    assert normalize_memory_type_label("unrecognized") == "custom"
    assert normalize_memory_type_label("fact") == "fact"


async def test_local_classifier_other_label_is_storable(monkeypatch) -> None:
    class Response:
        status_code = 200

        def json(self):
            return {"predictions": [{"label": "other", "score": 0.8}]}

    async def fake_post(*args, **kwargs):
        return Response()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    settings = Settings(engine_mode="offline")
    response = await LLMService(settings).complete_json(
        json.dumps({"messages": [{"speaker": "User", "text": "A miscellaneous note."}]})
    )

    assert response["memories"][0]["memory_type"] == "fact"


def test_heuristic_memory_type_inference() -> None:
    assert infer_memory_type("I prefer tea") == "preference"
    assert infer_memory_type("I started a new job yesterday") == "event"
    assert infer_memory_type("I am learning Rust") == "skill"
    assert infer_memory_type("A miscellaneous note") == "fact"

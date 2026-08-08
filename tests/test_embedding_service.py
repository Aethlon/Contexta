"""Tests for embedding service behavior."""

from uuid import uuid4

from contexta.config.settings import Settings
from contexta.models.memory import MemoryRecord
from contexta.services.embedding import DeterministicEmbeddingProvider, EmbeddingService


class FakeProvider:
    def __init__(self, embedding: list[float] | None = None, error: Exception | None = None) -> None:
        self.embedding = embedding or [0.1, 0.2, 0.3]
        self.error = error

    async def embed(self, text: str) -> list[float]:
        if self.error:
            raise self.error
        return self.embedding


class FakeMemoryRepository:
    def __init__(self) -> None:
        self.updates = []

    async def update_by_id(self, record_id, values: dict) -> int:
        self.updates.append((record_id, values))
        return 1


def settings() -> Settings:
    return Settings(embedding_dimensions=3, embedding_provider="deterministic")


def memory() -> MemoryRecord:
    return MemoryRecord(
        id=uuid4(),
        user_id=uuid4(),
        organization_id=uuid4(),
        memory_type="fact",
        title="contexta",
        content="contexta uses embeddings.",
        source_type="user_explicit",
        confidence=1.0,
        importance=0.5,
    )


async def test_generate_and_store_updates_embedding() -> None:
    repo = FakeMemoryRepository()
    record = memory()
    service = EmbeddingService(settings=settings(), provider=FakeProvider())

    stored = await service.generate_and_store(record, repo)

    assert stored is True
    assert record.embedding == [0.1, 0.2, 0.3]
    assert repo.updates == [(record.id, {"embedding": [0.1, 0.2, 0.3]})]


async def test_embedding_failure_degrades_gracefully_and_enqueues_retry() -> None:
    repo = FakeMemoryRepository()
    record = memory()
    retries = []

    async def retry(memory_id):
        retries.append(memory_id)

    service = EmbeddingService(
        settings=settings(),
        provider=FakeProvider(error=RuntimeError("provider unavailable")),
        retry_enqueue=retry,
    )

    stored = await service.generate_and_store(record, repo)

    assert stored is False
    assert repo.updates == []
    assert retries == [record.id]


async def test_deterministic_provider_returns_configured_dimensions() -> None:
    provider = DeterministicEmbeddingProvider(dimensions=5)

    embedding = await provider.embed("hello")

    assert len(embedding) == 5
    assert all(-1.0 <= value <= 1.0 for value in embedding)

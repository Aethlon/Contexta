"""Tests for memory deduplication thresholds and scope."""

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from contexta.core.extraction.deduplication import MemoryDeduplicator
from contexta.core.schemas import ExtractedMemory, ObservationPayload
from contexta.core.types import MemoryType, SourceType


@dataclass
class ExistingMemory:
    id: UUID
    user_id: UUID
    organization_id: UUID
    memory_type: str
    title: str
    content: str
    structured_data: dict | None = None
    tags: list[str] | None = None


class FixedSimilarity:
    def __init__(self, score: float) -> None:
        self.score = score

    async def similarity(self, left: str, right: str) -> float:
        return self.score


class FakeMemoryRepository:
    def __init__(self, records: list[ExistingMemory]) -> None:
        self.records = records
        self.updates: list[tuple[UUID, dict]] = []

    async def get_by_type(
        self,
        user_id: UUID,
        memory_type: MemoryType,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ExistingMemory]:
        return [
            record
            for record in self.records
            if record.user_id == user_id and record.memory_type == memory_type.value
        ]

    async def update_by_id(self, record_id: UUID, values: dict) -> int:
        self.updates.append((record_id, values))
        return 1


@pytest.fixture
def payload() -> ObservationPayload:
    return ObservationPayload(
        user_id=uuid4(),
        organization_id=uuid4(),
        session_id=uuid4(),
        messages=[{"role": "user", "content": "Remember I prefer Python."}],
    )


def extracted_memory() -> ExtractedMemory:
    return ExtractedMemory(
        memory_type=MemoryType.PREFERENCE,
        source_type=SourceType.USER_EXPLICIT,
        title="Prefers Python",
        content="The user prefers Python.",
        tags=["python"],
    )


async def test_duplicate_above_threshold_is_discarded(payload: ObservationPayload) -> None:
    existing = ExistingMemory(
        id=uuid4(),
        user_id=payload.user_id,
        organization_id=payload.organization_id,
        memory_type=MemoryType.PREFERENCE.value,
        title="Python preference",
        content="The user prefers Python.",
    )
    repo = FakeMemoryRepository([existing])
    deduplicator = MemoryDeduplicator(repo, FixedSimilarity(0.96))

    result = await deduplicator.deduplicate(payload, extracted_memory())

    assert result.action == "discard"
    assert result.existing_id == existing.id
    assert repo.updates[0][0] == existing.id
    assert "updated_at" in repo.updates[0][1]


async def test_near_duplicate_is_merged(payload: ObservationPayload) -> None:
    existing = ExistingMemory(
        id=uuid4(),
        user_id=payload.user_id,
        organization_id=payload.organization_id,
        memory_type=MemoryType.PREFERENCE.value,
        title="Python preference",
        content="The user likes Python.",
        structured_data={"language": "python"},
        tags=["backend"],
    )
    repo = FakeMemoryRepository([existing])
    deduplicator = MemoryDeduplicator(repo, FixedSimilarity(0.9))

    result = await deduplicator.deduplicate(payload, extracted_memory())

    assert result.action == "merge"
    update = repo.updates[0][1]
    assert "The user prefers Python." in update["content"]
    assert update["tags"] == ["backend", "python"]


async def test_low_similarity_is_stored(payload: ObservationPayload) -> None:
    existing = ExistingMemory(
        id=uuid4(),
        user_id=payload.user_id,
        organization_id=payload.organization_id,
        memory_type=MemoryType.PREFERENCE.value,
        title="Editor preference",
        content="The user prefers Vim.",
    )
    repo = FakeMemoryRepository([existing])
    deduplicator = MemoryDeduplicator(repo, FixedSimilarity(0.5))

    result = await deduplicator.deduplicate(payload, extracted_memory())

    assert result.action == "store"
    assert result.memory == extracted_memory()
    assert repo.updates == []


async def test_candidates_are_scoped_to_user_and_memory_type(
    payload: ObservationPayload,
) -> None:
    repo = FakeMemoryRepository(
        [
            ExistingMemory(
                id=uuid4(),
                user_id=uuid4(),
                organization_id=payload.organization_id,
                memory_type=MemoryType.PREFERENCE.value,
                title="Other user",
                content="The user prefers Python.",
            ),
            ExistingMemory(
                id=uuid4(),
                user_id=payload.user_id,
                organization_id=payload.organization_id,
                memory_type=MemoryType.FACT.value,
                title="Wrong type",
                content="The user prefers Python.",
            ),
        ]
    )
    deduplicator = MemoryDeduplicator(repo, FixedSimilarity(1.0))

    result = await deduplicator.deduplicate(payload, extracted_memory())

    assert result.action == "store"
    assert repo.updates == []

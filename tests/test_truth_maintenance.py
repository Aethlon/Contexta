"""Tests for truth maintenance and supersession."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from contexta.core.truth.maintenance import TruthMaintenanceEngine
from contexta.models.memory import MemoryRecord


class AlwaysContradicts:
    async def contradicts(self, new_memory: MemoryRecord, existing_memory: object) -> bool:
        return True


class NeverContradicts:
    async def contradicts(self, new_memory: MemoryRecord, existing_memory: object) -> bool:
        return False


class FakeMemoryRepository:
    def __init__(self, memories: list[MemoryRecord]) -> None:
        self.memories = memories
        self.superseded: list[tuple[UUID, datetime]] = []

    async def get_current_truths(
        self,
        user_id: UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        return [
            memory
            for memory in self.memories
            if memory.user_id == user_id and memory.valid_to is None
        ]

    async def supersede(self, old_id: UUID, valid_to: datetime) -> int:
        self.superseded.append((old_id, valid_to))
        for memory in self.memories:
            if memory.id == old_id:
                memory.valid_to = valid_to
        return 1


class FakeCreateRepository:
    def __init__(self) -> None:
        self.records = []

    async def create(self, record):
        self.records.append(record)
        return record


def make_memory(
    *,
    user_id: UUID,
    organization_id: UUID,
    title: str,
    content: str,
    memory_type: str = "fact",
) -> MemoryRecord:
    now = datetime.now(timezone.utc)
    return MemoryRecord(
        id=uuid4(),
        user_id=user_id,
        organization_id=organization_id,
        memory_type=memory_type,
        title=title,
        content=content,
        structured_data={"source": "test"},
        source_type="user_explicit",
        confidence=1.0,
        importance=0.7,
        session_id=uuid4(),
        valid_from=now,
        valid_to=None,
    )


async def test_contradiction_supersedes_old_memory_and_preserves_version() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    old = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Preferred language",
        content="The user prefers JavaScript.",
    )
    new = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Preferred language",
        content="The user prefers Python.",
    )
    memory_repo = FakeMemoryRepository([old])
    version_repo = FakeCreateRepository()
    edge_repo = FakeCreateRepository()
    audit_repo = FakeCreateRepository()
    entity_id = uuid4()
    engine = TruthMaintenanceEngine(
        memory_repo,
        version_repo,
        edge_repository=edge_repo,
        audit_repository=audit_repo,
        contradiction_detector=AlwaysContradicts(),
    )

    result = await engine.apply(new, entity_ids=[entity_id])

    assert len(result) == 1
    assert old.valid_to == result[0].valid_to
    assert memory_repo.superseded == [(old.id, result[0].valid_to)]
    assert version_repo.records[0].memory_id == old.id
    assert version_repo.records[0].superseded_by_id == new.id
    assert version_repo.records[0].content == "The user prefers JavaScript."
    assert edge_repo.records[0].relationship_type == "superseded_by"
    assert audit_repo.records[0].operation_type == "memory_superseded"


async def test_non_contradiction_leaves_current_truth_unchanged() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    old = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Preferred language",
        content="The user prefers JavaScript.",
    )
    new = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Favorite database",
        content="The user prefers Postgres.",
    )
    memory_repo = FakeMemoryRepository([old])
    version_repo = FakeCreateRepository()
    engine = TruthMaintenanceEngine(
        memory_repo,
        version_repo,
        contradiction_detector=NeverContradicts(),
    )

    assert await engine.apply(new) == []
    assert old.valid_to is None
    assert version_repo.records == []


async def test_truth_candidates_are_same_user_and_type_only() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    other_type = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Preferred language",
        content="The user prefers JavaScript.",
        memory_type="preference",
    )
    new = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Preferred language",
        content="The user prefers Python.",
        memory_type="fact",
    )
    memory_repo = FakeMemoryRepository([other_type])
    version_repo = FakeCreateRepository()
    engine = TruthMaintenanceEngine(
        memory_repo,
        version_repo,
        contradiction_detector=AlwaysContradicts(),
    )

    assert await engine.apply(new) == []
    assert version_repo.records == []

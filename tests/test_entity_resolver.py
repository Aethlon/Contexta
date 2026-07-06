"""Tests for entity resolution and graph linking."""

from uuid import UUID, uuid4
from datetime import datetime, timezone

import pytest

from contexta.core.entities.resolver import EntityResolver
from contexta.core.schemas import ExtractedMemory, ObservationPayload
from contexta.core.types import EntityType, MemoryType, RelationType, SourceType
from contexta.models.entity import Entity


class FixedSimilarity:
    def __init__(self, score: float) -> None:
        self.score = score

    async def similarity(self, left: str, right: str) -> float:
        return self.score


class FakeEntityRepository:
    def __init__(self, entities: list[Entity]) -> None:
        self.entities = entities
        self.updates: list[tuple[UUID, dict]] = []

    async def get_by_user(
        self,
        user_id: UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Entity]:
        return [entity for entity in self.entities if entity.user_id == user_id]

    async def create(self, record: Entity) -> Entity:
        record.id = uuid4()
        self.entities.append(record)
        return record

    async def update_by_id(self, record_id: UUID, values: dict) -> int:
        self.updates.append((record_id, values))
        return 1


class FakeLinkRepository:
    def __init__(self) -> None:
        self.links = []

    async def create(self, record):
        self.links.append(record)
        return record


class FakeEdgeRepository:
    def __init__(self) -> None:
        self.edges = []

    async def create(self, record):
        self.edges.append(record)
        return record


@pytest.fixture
def payload() -> ObservationPayload:
    return ObservationPayload(
        user_id=uuid4(),
        organization_id=uuid4(),
        session_id=uuid4(),
        messages=[{"role": "user", "content": "Working on contexta with FastAPI."}],
    )


def memory_with_entity(name: str = "contexta") -> ExtractedMemory:
    return ExtractedMemory(
        memory_type=MemoryType.PROJECT,
        source_type=SourceType.USER_EXPLICIT,
        title="Project update",
        content="Working on the contexta project.",
        entities=[name],
    )


async def test_high_confidence_match_links_existing_entity(
    payload: ObservationPayload,
) -> None:
    existing = Entity(
        id=uuid4(),
        organization_id=payload.organization_id,
        user_id=payload.user_id,
        entity_type=EntityType.PROJECT.value,
        name="contexta",
        last_updated=datetime.now(timezone.utc),
    )
    entities = FakeEntityRepository([existing])
    links = FakeLinkRepository()
    resolver = EntityResolver(entities, links, similarity_provider=FixedSimilarity(0.81))

    result = await resolver.resolve_memory_entities(
        payload=payload,
        memory_id=uuid4(),
        memory=memory_with_entity(),
    )

    assert len(result) == 1
    assert result[0].created is False
    assert result[0].entity.id == existing.id
    assert len(links.links) == 1
    assert entities.updates[0][0] == existing.id


async def test_low_confidence_creates_new_entity(payload: ObservationPayload) -> None:
    entities = FakeEntityRepository([])
    links = FakeLinkRepository()
    resolver = EntityResolver(entities, links, similarity_provider=FixedSimilarity(0.2))

    result = await resolver.resolve_memory_entities(
        payload=payload,
        memory_id=uuid4(),
        memory=memory_with_entity("New Project"),
    )

    assert len(result) == 1
    assert result[0].created is True
    assert result[0].entity.name == "New Project"
    assert result[0].entity.organization_id == payload.organization_id
    assert len(links.links) == 1


async def test_infers_supported_entity_types(payload: ObservationPayload) -> None:
    entities = FakeEntityRepository([])
    links = FakeLinkRepository()
    resolver = EntityResolver(entities, links)

    result = await resolver.resolve_memory_entities(
        payload=payload,
        memory_id=uuid4(),
        memory=memory_with_entity("FastAPI"),
    )

    assert result[0].entity.entity_type == EntityType.TECHNOLOGY.value


async def test_create_typed_edge(payload: ObservationPayload) -> None:
    entities = FakeEntityRepository([])
    links = FakeLinkRepository()
    edges = FakeEdgeRepository()
    resolver = EntityResolver(entities, links, edges)
    source_id = uuid4()
    target_id = uuid4()

    edge = await resolver.create_edge(
        source_entity_id=source_id,
        target_entity_id=target_id,
        organization_id=payload.organization_id,
        relationship_type=RelationType.USES,
    )

    assert edge.relationship_type == RelationType.USES.value
    assert edge.source_entity_id == source_id
    assert edge.target_entity_id == target_id
    assert edges.edges == [edge]

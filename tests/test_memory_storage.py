"""Tests for memory storage pipeline repository entry point."""

from uuid import uuid4

from contexta.core.schemas import ExtractedMemory
from contexta.core.types import MemoryType, RelationType, SourceType
from contexta.models.entity import EntityEdge
from contexta.repositories.memory_repo import MemoryRepository


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.flush_count = 0

    def add(self, record) -> None:
        self.added.append(record)

    async def flush(self) -> None:
        self.flush_count += 1


def make_memory() -> ExtractedMemory:
    return ExtractedMemory(
        memory_type=MemoryType.PROJECT,
        source_type=SourceType.USER_EXPLICIT,
        title="contexta core engine",
        content="The user is building the contexta core engine.",
        structured_data={"repo": "contexta"},
        tags=["contexta", "python"],
    )


async def test_persist_stores_required_memory_fields() -> None:
    organization_id = uuid4()
    user_id = uuid4()
    session_id = uuid4()
    session = FakeSession()
    repo = MemoryRepository(session, tenant_id=organization_id)

    record = await repo.persist(
        user_id=user_id,
        organization_id=organization_id,
        session_id=session_id,
        memory=make_memory(),
        confidence=1.0,
        importance=0.8,
        utility_score=0.2,
        is_pinned=True,
    )

    assert record in session.added
    assert record.user_id == user_id
    assert record.organization_id == organization_id
    assert record.memory_type == "project"
    assert record.title == "contexta core engine"
    assert record.source_type == "user_explicit"
    assert record.confidence == 1.0
    assert record.importance == 0.8
    assert record.utility_score == 0.2
    assert record.tags == ["contexta", "python"]
    assert record.session_id == session_id
    assert record.memory_state == "active"
    assert record.is_pinned is True
    assert record.is_archived is False
    assert record.valid_to is None


async def test_persist_stores_graph_edges() -> None:
    organization_id = uuid4()
    session = FakeSession()
    repo = MemoryRepository(session, tenant_id=organization_id)
    edge = EntityEdge(
        source_entity_id=uuid4(),
        target_entity_id=uuid4(),
        organization_id=organization_id,
        relationship_type=RelationType.RELATED_TO.value,
    )

    await repo.persist(
        user_id=uuid4(),
        organization_id=organization_id,
        session_id=None,
        memory=make_memory(),
        confidence=0.9,
        importance=0.7,
        graph_edges=[edge],
    )

    assert edge in session.added
    assert session.flush_count == 2

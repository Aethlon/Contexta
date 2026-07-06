"""Tests for hybrid retrieval engine."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from contexta.core.retrieval.engine import RetrievalEngine
from contexta.core.schemas import RetrievalQuery
from contexta.models.entity import EntityEdge, MemoryEntityLink
from contexta.models.memory import MemoryRecord


class FakeMemoryRepository:
    def __init__(self, memories: list[MemoryRecord]) -> None:
        self.memories = memories

    async def get_by_user(
        self,
        user_id: UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        return [memory for memory in self.memories if memory.user_id == user_id]


class FakeLinkRepository:
    def __init__(self, links: dict[UUID, list[MemoryEntityLink]]) -> None:
        self.links = links

    async def get_memories_for_entity(self, entity_id: UUID) -> list[MemoryEntityLink]:
        return self.links.get(entity_id, [])


class FakeEdgeRepository:
    def __init__(self, edges: dict[UUID, list[EntityEdge]]) -> None:
        self.edges = edges

    async def get_neighbors(self, entity_id: UUID) -> list[EntityEdge]:
        return self.edges.get(entity_id, [])


def make_memory(
    *,
    user_id: UUID,
    organization_id: UUID,
    title: str,
    content: str,
    importance: float = 0.5,
    embedding: list[float] | None = None,
    memory_state: str = "active",
    is_archived: bool = False,
    created_at: datetime | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        id=uuid4(),
        user_id=user_id,
        organization_id=organization_id,
        memory_type="project",
        title=title,
        content=content,
        source_type="user_explicit",
        confidence=1.0,
        importance=importance,
        embedding=embedding,
        memory_state=memory_state,
        is_archived=is_archived,
        valid_to=None,
        created_at=created_at or datetime.now(timezone.utc),
    )


def query(user_id: UUID, organization_id: UUID) -> RetrievalQuery:
    return RetrievalQuery(
        user_id=user_id,
        organization_id=organization_id,
        query_text="python contexta",
        limit=10,
    )


async def test_retrieval_combines_semantic_keyword_importance_and_recency() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    now = datetime.now(timezone.utc)
    strong = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="contexta Python project",
        content="Uses Python heavily.",
        importance=0.9,
        embedding=[1.0, 0.0],
        created_at=now,
    )
    weak = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Other work",
        content="Unrelated note.",
        importance=0.2,
        embedding=[0.0, 1.0],
        created_at=now - timedelta(days=90),
    )
    engine = RetrievalEngine(FakeMemoryRepository([weak, strong]))

    results = await engine.retrieve(query(user_id, organization_id), query_embedding=[1.0, 0.0], now=now)

    assert results[0].memory == strong
    assert results[0].semantic_score == 1.0
    assert results[0].keyword_score == 1.0


async def test_retrieval_filters_archived_by_default() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    archived = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Archived contexta",
        content="python",
        is_archived=True,
    )
    engine = RetrievalEngine(FakeMemoryRepository([archived]))

    assert await engine.retrieve(query(user_id, organization_id)) == []


async def test_cold_state_penalty_reduces_score() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    now = datetime.now(timezone.utc)
    active = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Active",
        content="python contexta",
        embedding=[1.0],
        created_at=now,
    )
    cold = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Cold",
        content="python contexta",
        embedding=[1.0],
        memory_state="cold",
        created_at=now,
    )
    engine = RetrievalEngine(FakeMemoryRepository([cold, active]))

    results = await engine.retrieve(query(user_id, organization_id), query_embedding=[1.0], now=now)

    assert results[0].memory == active
    assert results[0].score > results[1].score


async def test_graph_expansion_contributes_graph_score() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    entity_id = uuid4()
    memory = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Graph memory",
        content="Linked project",
    )
    link = MemoryEntityLink(
        memory_id=memory.id,
        entity_id=entity_id,
        organization_id=organization_id,
    )
    engine = RetrievalEngine(
        FakeMemoryRepository([memory]),
        link_repository=FakeLinkRepository({entity_id: [link]}),
    )

    results = await engine.retrieve(query(user_id, organization_id), seed_entity_ids=[entity_id])

    assert results[0].graph_score == 1.0

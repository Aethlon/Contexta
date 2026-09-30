"""Tests for hybrid retrieval engine."""

from datetime import UTC, datetime, timedelta
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


class ChannelMemoryRepository:
    def __init__(
        self,
        memories: list[MemoryRecord],
        *,
        dense: list[MemoryRecord],
        lexical: list[MemoryRecord],
    ) -> None:
        self.memories = memories
        self.dense = dense
        self.lexical = lexical
        self.dense_calls = 0
        self.lexical_calls = 0

    async def get_by_user(
        self,
        user_id: UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        return [memory for memory in self.memories if memory.user_id == user_id]

    async def get_by_vector_similarity(
        self,
        user_id: UUID,
        embedding: list[float],
        *,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        self.dense_calls += 1
        return self.dense

    async def get_by_lexical_similarity(
        self,
        user_id: UUID,
        query_text: str,
        *,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        self.lexical_calls += 1
        return self.lexical

    async def get_many_by_ids(self, memory_ids: list[UUID]) -> list[MemoryRecord]:
        wanted = set(memory_ids)
        return [memory for memory in self.memories if memory.id in wanted]


class ExpandingLinkRepository:
    def __init__(
        self,
        memory_links: dict[UUID, list[MemoryEntityLink]],
        entity_links: dict[UUID, list[MemoryEntityLink]],
    ) -> None:
        self.memory_links = memory_links
        self.entity_links = entity_links
        self.memory_queries: list[UUID] = []
        self.entity_queries: list[UUID] = []

    async def get_entities_for_memory(
        self,
        memory_id: UUID,
    ) -> list[MemoryEntityLink]:
        self.memory_queries.append(memory_id)
        return self.memory_links.get(memory_id, [])

    async def get_memories_for_entity(
        self,
        entity_id: UUID,
    ) -> list[MemoryEntityLink]:
        self.entity_queries.append(entity_id)
        return self.entity_links.get(entity_id, [])


class CaptureReranker:
    def __init__(self) -> None:
        self.pool_sizes: list[int] = []

    async def rerank(self, query, results):
        self.pool_sizes.append(len(results))
        return results


class DepthRecordingEngine(RetrievalEngine):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.graph_depths: list[int] = []

    async def _graph_memory_weights(self, seed_entity_ids, *, max_depth):
        self.graph_depths.append(max_depth)
        return await super()._graph_memory_weights(
            seed_entity_ids,
            max_depth=max_depth,
        )


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
    event_at: datetime | None = None,
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
        created_at=created_at or datetime.now(UTC),
        event_at=event_at,
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
    now = datetime.now(UTC)
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
    now = datetime.now(UTC)
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


async def test_retrieval_uses_independent_lexical_candidates_without_filler() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    dense = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Dense result",
        content="Unrelated semantic note",
        embedding=[1.0, 0.0],
    )
    lexical = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Contexta Python",
        content="Python contexta lexical result",
        embedding=[0.0, 1.0],
    )
    filler = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Filler",
        content="No channel evidence",
        embedding=[0.0, 1.0],
    )
    repository = ChannelMemoryRepository(
        [dense, lexical, filler],
        dense=[dense],
        lexical=[lexical],
    )
    engine = RetrievalEngine(repository, enable_dense_escalation=False)

    results = await engine.retrieve(
        query(user_id, organization_id),
        query_embedding=[1.0, 0.0],
    )

    assert repository.dense_calls == 1
    assert repository.lexical_calls == 1
    assert {result.memory.id for result in results} == {dense.id, lexical.id}
    assert filler.id not in {result.memory.id for result in results}


async def test_graph_expansion_hydrates_memory_outside_dense_pool() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    entity_id = uuid4()
    anchor = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Dense anchor",
        content="Semantic anchor",
        embedding=[1.0, 0.0],
    )
    linked = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Linked fact",
        content="Graph-only detail",
    )
    anchor_link = MemoryEntityLink(
        memory_id=anchor.id,
        entity_id=entity_id,
        organization_id=organization_id,
    )
    linked_link = MemoryEntityLink(
        memory_id=linked.id,
        entity_id=entity_id,
        organization_id=organization_id,
    )
    memory_repository = ChannelMemoryRepository(
        [anchor, linked],
        dense=[anchor],
        lexical=[],
    )
    link_repository = ExpandingLinkRepository(
        {anchor.id: [anchor_link]},
        {entity_id: [anchor_link, linked_link]},
    )
    engine = RetrievalEngine(
        memory_repository,
        link_repository=link_repository,
    )

    results = await engine.retrieve(
        query(user_id, organization_id),
        query_embedding=[1.0, 0.0],
    )

    result_ids = {result.memory.id for result in results}
    assert anchor.id in result_ids
    assert linked.id in result_ids
    assert next(result for result in results if result.memory.id == linked.id).graph_score > 0.0


async def test_reranker_receives_only_bounded_fused_pool() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    memories = [
        make_memory(
            user_id=user_id,
            organization_id=organization_id,
            title=f"Contexta Python {index}",
            content=f"Python contexta memory {index}",
            embedding=[1.0, 0.0],
        )
        for index in range(100)
    ]
    repository = ChannelMemoryRepository(
        memories,
        dense=memories,
        lexical=memories,
    )
    reranker = CaptureReranker()
    engine = RetrievalEngine(repository, reranker=reranker)
    retrieval_query = query(user_id, organization_id).model_copy(update={"limit": 100})

    results = await engine.retrieve(
        retrieval_query,
        query_embedding=[1.0, 0.0],
    )

    assert reranker.pool_sizes == [RetrievalEngine.RERANK_POOL_SIZE]
    assert len(results) == RetrievalEngine.RERANK_POOL_SIZE


async def test_comparative_query_uses_depth_two_and_promotes_each_entity() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    now = datetime.now(UTC)
    filler = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Shared filler",
        content="Unrelated context",
        embedding=[1.0, 0.0],
    )
    jon = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Jon fact",
        content="Jon started a business",
        embedding=[1.0, 0.0],
    )
    gina = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Gina fact",
        content="Gina started a business",
        embedding=[1.0, 0.0],
    )
    repository = ChannelMemoryRepository(
        [filler, jon, gina],
        dense=[filler, jon, gina],
        lexical=[filler, jon, gina],
    )
    engine = DepthRecordingEngine(
        repository,
        link_repository=ExpandingLinkRepository({}, {}),
    )
    comparison_query = query(user_id, organization_id).model_copy(
        update={
            "query_text": "What do Jon and Gina both have in common?",
            "graph_depth": 0,
            "limit": 2,
        }
    )

    results = await engine.retrieve(
        comparison_query,
        query_embedding=[1.0, 0.0],
        seed_entity_ids=[uuid4(), uuid4()],
        now=now,
    )

    assert engine.graph_depths[0] == 2
    assert {result.memory.id for result in results} == {jon.id, gina.id}


async def test_graph_expansion_uses_top_five_dense_and_lexical_anchors() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    dense = [
        make_memory(
            user_id=user_id,
            organization_id=organization_id,
            title=f"Dense anchor {index}",
            content=f"Dense result {index}",
            embedding=[1.0, 0.0],
        )
        for index in range(5)
    ]
    lexical = [
        make_memory(
            user_id=user_id,
            organization_id=organization_id,
            title=f"Lexical anchor {index}",
            content=f"Lexical result {index}",
            embedding=[1.0, 0.0],
        )
        for index in range(5)
    ]
    memory_links: dict[UUID, list[MemoryEntityLink]] = {}
    for memory in [*dense, *lexical]:
        entity_id = uuid4()
        memory_links[memory.id] = [
            MemoryEntityLink(
                memory_id=memory.id,
                entity_id=entity_id,
                organization_id=organization_id,
            )
        ]
    repository = ChannelMemoryRepository(
        [*dense, *lexical],
        dense=dense,
        lexical=lexical,
    )
    link_repository = ExpandingLinkRepository(memory_links, {})
    # The cascade is the default now, and a sufficient primary pass never fetches
    # dense candidates, so there would be no dense anchors to widen the graph
    # from. This test is about the 5+5 anchor set, so it opts out explicitly.
    engine = RetrievalEngine(
        repository,
        link_repository=link_repository,
        enable_dense_escalation=False,
    )

    await engine.retrieve(query(user_id, organization_id), query_embedding=[1.0, 0.0])

    assert set(link_repository.memory_queries) == {
        memory.id for memory in [*dense, *lexical]
    }


async def test_temporal_intent_uses_event_at_for_year_and_explicit_dates() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    now = datetime(2024, 1, 1, tzinfo=UTC)
    event_memory = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Project milestone",
        content="A project milestone happened",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        event_at=datetime(2023, 5, 3, tzinfo=UTC),
    )
    engine = RetrievalEngine(FakeMemoryRepository([event_memory]))

    for text in (
        "Which year did the project start?",
        "What year did the project start?",
        "What happened in 2023?",
        "Tell me about the beginning of May 2023.",
        "What happened on May 3, 2023?",
    ):
        temporal_query = query(user_id, organization_id).model_copy(
            update={"query_text": text}
        )
        assert engine._temporal_relevance(temporal_query, event_memory, now) > 0.0

    wrong_event_memory = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Older project milestone",
        content="A different project milestone",
        created_at=datetime(2023, 5, 3, tzinfo=UTC),
        event_at=datetime(2022, 5, 3, tzinfo=UTC),
    )
    year_query = query(user_id, organization_id).model_copy(
        update={"query_text": "What happened in 2023?"}
    )
    date_query = query(user_id, organization_id).model_copy(
        update={"query_text": "What happened on May 3, 2023?"}
    )
    assert engine._temporal_relevance(year_query, wrong_event_memory, now) == 0.0
    assert engine._temporal_relevance(date_query, wrong_event_memory, now) == 0.0


async def test_fallback_keyword_matching_normalizes_went_and_mom() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    memory = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Family update",
        content="My mother went to the park.",
    )
    engine = RetrievalEngine(FakeMemoryRepository([memory]))
    synonym_query = query(user_id, organization_id).model_copy(
        update={"query_text": "mom went to the park"}
    )

    results = await engine.retrieve(synonym_query)

    assert results[0].memory == memory
    assert results[0].keyword_score == 1.0

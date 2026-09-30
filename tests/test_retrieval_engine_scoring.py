"""Scoring-path guards for `RetrievalEngine`.

These cover the properties that were wrong in the scoring layer rather than the
behaviour of any one channel:

1. Fusion must not freeze the head of the page onto one score
   (`weighted_reciprocal_rank_fusion` clamps its normalised RRF term only).
2. A graph outage must contribute no graph weight, never the maximum weight.
3. The cold penalty is applied once, not squared.
4. Entity-coverage promotion may not splice a below-threshold row in above a
   row that outscores it.
5. The cascade is the default channel order, and the non-cascade path still
   populates `mentioned_entities`.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from contexta.core.retrieval.engine import RetrievalEngine, RetrievalResult
from contexta.core.retrieval.fusion import FusedCandidate
from contexta.core.schemas import RetrievalQuery
from contexta.models.entity import MemoryEntityLink
from contexta.models.memory import MemoryRecord


def make_memory(
    *,
    user_id: UUID,
    organization_id: UUID,
    title: str,
    content: str = "",
    embedding: list[float] | None = None,
    memory_state: str = "active",
    importance: float = 0.5,
    confidence: float = 1.0,
    utility_score: float | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        id=uuid4(),
        user_id=user_id,
        organization_id=organization_id,
        memory_type="project",
        title=title,
        content=content,
        source_type="user_explicit",
        confidence=confidence,
        importance=importance,
        utility_score=utility_score,
        embedding=embedding,
        memory_state=memory_state,
        is_archived=False,
        valid_to=None,
        created_at=datetime.now(UTC),
    )


def make_query(
    user_id: UUID,
    organization_id: UUID,
    *,
    text: str = "contexta retrieval",
    limit: int = 10,
) -> RetrievalQuery:
    return RetrievalQuery(
        user_id=user_id,
        organization_id=organization_id,
        query_text=text,
        limit=limit,
    )


def make_result(
    memory: MemoryRecord,
    score: float,
) -> RetrievalResult:
    return RetrievalResult(
        memory=memory,
        score=score,
        semantic_score=0.0,
        graph_score=0.0,
        importance_score=0.0,
        recency_score=0.0,
        keyword_score=0.0,
    )


class MemoryRepository:
    """Minimal repository: no channel methods, so fallback reads are used."""

    def __init__(self, memories: list[MemoryRecord]) -> None:
        self.memories = memories
        self.id_batches: list[list[UUID]] = []

    async def get_by_user(
        self,
        user_id: UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        return [memory for memory in self.memories if memory.user_id == user_id]

    async def get_many_by_ids(self, memory_ids: list[UUID]) -> list[MemoryRecord]:
        self.id_batches.append(list(memory_ids))
        wanted = set(memory_ids)
        return [memory for memory in self.memories if memory.id in wanted]


class LinkRepository:
    """Link repository offering the bulk reads the engine prefers."""

    def __init__(self, links: list[MemoryEntityLink]) -> None:
        self.links = links
        self.bulk_entity_calls: list[list[UUID]] = []

    async def bulk_get_memories_for_entities(
        self,
        entity_ids: list[UUID],
    ) -> list[MemoryEntityLink]:
        self.bulk_entity_calls.append(list(entity_ids))
        wanted = set(entity_ids)
        return [link for link in self.links if link.entity_id in wanted]

    async def get_memories_for_entity(
        self,
        entity_id: UUID,
    ) -> list[MemoryEntityLink]:
        raise AssertionError("the per-entity read is the N+1 the bulk call replaces")

    async def bulk_get_entities_for_memories(
        self,
        memory_ids: list[UUID],
    ) -> list[MemoryEntityLink]:
        wanted = set(memory_ids)
        return [link for link in self.links if link.memory_id in wanted]


class FailingEdgeRepository:
    async def walk_entity_graph(self, **_kwargs) -> dict[UUID, int]:
        raise RuntimeError("recursive CTE failed")


class StaticEdgeRepository:
    def __init__(self, distances: dict[UUID, int]) -> None:
        self.distances = distances

    async def walk_entity_graph(self, **_kwargs) -> dict[UUID, int]:
        return dict(self.distances)


# 1. Fusion clamp -----------------------------------------------------------


async def test_same_channel_rank_different_sub_scores_score_differently() -> None:
    """Equal rank evidence must not decide the page on its own.

    `weighted_reciprocal_rank_fusion` used to clamp the *sum* of the normalised
    RRF term and the additive priors to 1.0. Both rows here have the same rank in
    the same channel and identical priors, so they used to come out of fusion
    with an identical score and were separated only by the engine's 0.20 feature
    term. At production settings that term is itself enough to pin both rows at
    1.0 once the clamp is present, which is what this asserts against: the two
    rows have to end up on two different scores.
    """
    user_id = uuid4()
    organization_id = uuid4()
    repository = MemoryRepository([])
    engine = RetrievalEngine(repository)
    retrieval_query = make_query(user_id, organization_id)

    aligned = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Contexta retrieval",
        content="Contexta retrieval",
        embedding=[1.0, 0.0],
        importance=0.5,
        confidence=1.0,
    )
    tangential = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Unrelated note",
        content="Nothing to do with the question",
        embedding=[1.0, 0.0],
        importance=0.5,
        confidence=1.0,
    )
    fused = [
        FusedCandidate(memory=aligned, score=1.0, channel_ranks=(("lexical", 1),)),
        FusedCandidate(memory=tangential, score=1.0, channel_ranks=(("lexical", 1),)),
    ]

    results = engine._score_candidates(
        fused,
        retrieval_query,
        query_embedding=[1.0, 0.0],
        graph_memory_weights={},
        now=datetime.now(UTC),
    )

    scores = {result.memory.id: result.score for result in results}
    assert scores[aligned.id] != scores[tangential.id]
    assert scores[aligned.id] > scores[tangential.id]


async def test_fusion_score_is_not_pinned_at_one_for_the_head_of_the_page() -> None:
    """Distinct fused scores have to survive the blend.

    The engine clamps its own blended score at 1.0, so a candidate that fusion
    scored above 1.0 -- which it now does, since fusion clamps its normalised
    RRF term alone -- would collapse onto 1.0 here. Two rows whose fused scores
    are close enough must still be separated by their features.
    """
    user_id = uuid4()
    organization_id = uuid4()
    engine = RetrievalEngine(MemoryRepository([]))
    retrieval_query = make_query(user_id, organization_id)

    dense = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Contexta retrieval",
        content="Contexta retrieval",
        embedding=[1.0, 0.0],
    )
    thin = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Unrelated note",
        content="Nothing to do with the question",
        embedding=[1.0, 0.0],
    )
    results = engine._score_candidates(
        [
            FusedCandidate(memory=dense, score=0.85, channel_ranks=(("lexical", 1),)),
            FusedCandidate(memory=thin, score=0.80, channel_ranks=(("lexical", 2),)),
        ],
        retrieval_query,
        query_embedding=[1.0, 0.0],
        graph_memory_weights={},
        now=datetime.now(UTC),
    )

    scores = {result.memory.id: result.score for result in results}
    assert scores[dense.id] > scores[thin.id]
    assert len(set(scores.values())) == 2


# 2. Graph-walk failure -----------------------------------------------------


async def test_raising_graph_walk_contributes_no_weights() -> None:
    """A graph outage must fail to zero, never to the maximum weight.

    Depth 0 is `1/sqrt(degree) * 0.5**0`, the best weight the channel can hand
    out, so the old `if not distances: return {seed: 0}` turned a thrown
    recursive CTE into a ranking boost for every seed's memories.
    """
    user_id = uuid4()
    organization_id = uuid4()
    seed = uuid4()
    memory = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Linked fact",
        content="Linked fact",
    )
    links = [
        MemoryEntityLink(memory_id=memory.id, entity_id=seed, organization_id=organization_id)
    ]
    engine = RetrievalEngine(
        MemoryRepository([memory]),
        link_repository=LinkRepository(links),
        edge_repository=FailingEdgeRepository(),
    )

    weights = await engine._graph_memory_weights([seed], max_depth=2)

    assert weights == {}

    results = await engine.retrieve(
        make_query(user_id, organization_id),
        seed_entity_ids=[seed],
    )
    assert all(result.graph_score == 0.0 for result in results)

    # Positive control: the same setup with a walk that answers hands the seed
    # the best weight the channel can give, which is exactly what the outage
    # used to be credited with.
    healthy = RetrievalEngine(
        MemoryRepository([memory]),
        link_repository=LinkRepository(links),
        edge_repository=StaticEdgeRepository({seed: 0}),
    )
    assert await healthy._graph_memory_weights([seed], max_depth=2) == {memory.id: 1.0}


async def test_successful_empty_walk_still_counts_the_seeds() -> None:
    """An edgeless graph is not an outage: the seed is at distance zero from itself."""
    user_id = uuid4()
    organization_id = uuid4()
    seed = uuid4()
    memory = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Linked fact",
        content="Linked fact",
    )
    links = [
        MemoryEntityLink(memory_id=memory.id, entity_id=seed, organization_id=organization_id)
    ]
    engine = RetrievalEngine(
        MemoryRepository([memory]),
        link_repository=LinkRepository(links),
        edge_repository=StaticEdgeRepository({}),
    )

    weights = await engine._graph_memory_weights([seed], max_depth=2)

    assert weights == {memory.id: 1.0}


async def test_graph_degree_is_one_bulk_read_and_ignores_superseded_rows() -> None:
    """Degree is a bulk read of current memories, not an N+1 over every link.

    `MemoryEntityLink` has no `valid_to`, so a fact the truth engine closed four
    times looked like a degree-4 hub and was divided by sqrt(4) -- the rows that
    had just been corrected were the ones the graph channel demoted hardest.
    """
    user_id = uuid4()
    organization_id = uuid4()
    entity_id = uuid4()
    current = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Current fact",
        content="Current fact",
    )
    superseded = [
        make_memory(
            user_id=user_id,
            organization_id=organization_id,
            title=f"Superseded {index}",
            content="Superseded fact",
        )
        for index in range(3)
    ]
    for memory in superseded:
        memory.valid_to = datetime.now(UTC)
    memories = [current, *superseded]
    links = [
        MemoryEntityLink(
            memory_id=memory.id,
            entity_id=entity_id,
            organization_id=organization_id,
        )
        for memory in memories
    ]
    link_repository = LinkRepository(links)
    engine = RetrievalEngine(
        MemoryRepository(memories),
        link_repository=link_repository,
        edge_repository=StaticEdgeRepository({entity_id: 0}),
    )

    weights = await engine._graph_memory_weights([entity_id], max_depth=2)

    # Degree 1, so weight 1.0 -- not 1/sqrt(4) shared with three closed rows.
    assert weights == {current.id: 1.0}
    assert link_repository.bulk_entity_calls == [[entity_id]]


# 3. Cold penalty -----------------------------------------------------------


async def test_cold_penalty_is_applied_once() -> None:
    """`0.7 * 0.7 = 0.49` used to demote a cold row by half, twice over."""
    user_id = uuid4()
    organization_id = uuid4()
    cold = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Contexta retrieval",
        content="Contexta retrieval",
        embedding=[1.0, 0.0],
        memory_state="cold",
    )
    active = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Contexta retrieval",
        content="Contexta retrieval",
        embedding=[1.0, 0.0],
        memory_state="active",
    )
    engine = RetrievalEngine(MemoryRepository([]))
    retrieval_query = make_query(user_id, organization_id)
    now = datetime.now(UTC)

    feature_score = engine._score_memory(
        retrieval_query,
        cold,
        query_embedding=[1.0, 0.0],
        graph_memory_weights={},
        now=now,
    ).score
    active_feature_score = engine._score_memory(
        retrieval_query,
        active,
        query_embedding=[1.0, 0.0],
        graph_memory_weights={},
        now=now,
    ).score

    # The feature score is a pure feature blend now: a cold row and its active
    # twin score identically there.
    assert feature_score == pytest.approx(active_feature_score)

    fused_score = 0.9
    [result] = engine._score_candidates(
        [FusedCandidate(memory=cold, score=fused_score, channel_ranks=(("lexical", 1),))],
        retrieval_query,
        query_embedding=[1.0, 0.0],
        graph_memory_weights={},
        now=now,
    )

    blend = 0.80 * fused_score + 0.20 * feature_score
    assert result.score == pytest.approx(0.7 * min(1.0, blend))
    # 0.49 is what the double penalty produced.
    assert result.score > 0.49 * blend


async def test_cold_and_identical_active_rows_differ_by_one_penalty() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    cold = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Contexta retrieval",
        content="Contexta retrieval",
        embedding=[1.0, 0.0],
        memory_state="cold",
    )
    active = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Contexta retrieval",
        content="Contexta retrieval",
        embedding=[1.0, 0.0],
        memory_state="active",
    )
    engine = RetrievalEngine(MemoryRepository([cold, active]))
    now = datetime.now(UTC)

    results = engine._score_candidates(
        [
            FusedCandidate(memory=active, score=0.9, channel_ranks=(("lexical", 1),)),
            FusedCandidate(memory=cold, score=0.9, channel_ranks=(("lexical", 1),)),
        ],
        make_query(user_id, organization_id),
        query_embedding=[1.0, 0.0],
        graph_memory_weights={},
        now=now,
    )
    by_id = {result.memory.id: result.score for result in results}

    assert by_id[cold.id] == pytest.approx(0.7 * by_id[active.id])
    assert by_id[cold.id] > 0.49 * by_id[active.id]


# 4. Coverage promotion ordering -------------------------------------------


async def test_promoted_row_cannot_displace_a_higher_scoring_result() -> None:
    """Promotion fills a declared gap; it must not re-rank the page.

    The eviction target used to be "the last slot" of a page that was already
    score-ordered, so a promoted row landed in the last position whatever it
    scored: a row worth 0.75 was published below rows worth 0.60, and the second
    promotion evicted the row above it. The promoted rows here score inside the
    page's range, which is the case the old placement got wrong.
    """
    user_id = uuid4()
    organization_id = uuid4()
    query = make_query(user_id, organization_id, text="What do Jon and Gina have in common?")
    engine = RetrievalEngine(MemoryRepository([]))

    def row(title: str, content: str, score: float) -> RetrievalResult:
        return make_result(
            make_memory(
                user_id=user_id,
                organization_id=organization_id,
                title=title,
                content=content,
            ),
            score,
        )

    page = [
        row(f"Row {index}", "Ranked evidence", score)
        for index, score in enumerate((0.90, 0.80, 0.70, 0.60, 0.50))
    ]
    # Both promoted rows score inside the page's range, and each is the only row
    # that mentions its entity.
    rex = row("Rex fact", "Rex started a business", 0.85)
    gina = row("Gina fact", "Gina started a business", 0.75)
    filler = [
        row(f"Filler {index}", "No entity here", score)
        for index, score in enumerate((0.40, 0.30))
    ]

    promoted = engine._promote_entity_coverage(
        query,
        [*page, *filler, rex, gina],
        entity_names=["rex", "gina"],
        result_limit=5,
    )

    scores = [result.score for result in promoted]
    promoted_ids = {result.memory.id for result in promoted}

    assert len(promoted) == 5
    # The page the caller receives is ordered by score, always.
    assert scores == sorted(scores, reverse=True)
    # The promotion still happened -- it is what makes a comparative answer
    # cover both entities -- and it evicted the page's two worst rows.
    assert {rex.memory.id, gina.memory.id} <= promoted_ids
    assert page[0].memory.id in promoted_ids
    assert page[4].memory.id not in promoted_ids
    assert page[3].memory.id not in promoted_ids
    assert all(result.memory.id != item.memory.id for result in promoted for item in filler)


async def test_promotion_orders_an_already_unordered_page() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    query = make_query(user_id, organization_id, text="Compare Jon and Gina")
    engine = RetrievalEngine(MemoryRepository([]))

    def row(title: str, content: str, score: float) -> RetrievalResult:
        return make_result(
            make_memory(
                user_id=user_id,
                organization_id=organization_id,
                title=title,
                content=content,
            ),
            score,
        )

    unsorted_page = [
        row("High", "Unrelated", 0.90),
        row("Bottom", "Unrelated", 0.10),
        row("Middle", "Unrelated", 0.50),
    ]
    for_low = row("For low", "Low entity row", 0.20)
    for_mid = row("For mid", "Mid entity row", 0.30)

    promoted = engine._promote_entity_coverage(
        query,
        [*unsorted_page, for_low, for_mid],
        entity_names=["low", "mid"],
        result_limit=3,
    )

    scores = [result.score for result in promoted]
    promoted_ids = {result.memory.id for result in promoted}

    assert scores == sorted(scores, reverse=True)
    assert len(promoted) == 3
    assert {for_low.memory.id, for_mid.memory.id} <= promoted_ids
    assert unsorted_page[0].memory.id in promoted_ids


async def test_required_evidence_is_still_forced_into_a_full_page() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    query = make_query(user_id, organization_id, text="Summarise the launch")
    engine = RetrievalEngine(MemoryRepository([]))

    page = [
        make_result(
            make_memory(
                user_id=user_id,
                organization_id=organization_id,
                title=f"Row {index}",
                content="Ranked evidence",
            ),
            score,
        )
        for index, score in enumerate((0.90, 0.80))
    ]
    required = make_result(
        make_memory(
            user_id=user_id,
            organization_id=organization_id,
            title="Required",
            content="Ranked evidence",
        ),
        0.05,
    )

    promoted = engine._promote_entity_coverage(
        query,
        [*page, required],
        entity_names=(),
        query_plan=_plan_with_required(query, [str(required.memory.id)]),
        result_limit=2,
    )

    promoted_ids = [result.memory.id for result in promoted]
    assert required.memory.id in promoted_ids
    assert len(promoted_ids) == 2
    # It displaced the worst row on the page, and the page is still ordered.
    assert promoted_ids[0] == page[0].memory.id
    assert [result.score for result in promoted] == sorted(
        (result.score for result in promoted),
        reverse=True,
    )


def _plan_with_required(query: RetrievalQuery, required_ids: list[str]):
    from contexta.core.retrieval.query_understanding import build_query_plan

    plan = build_query_plan(query.query_text, now=datetime.now(UTC))
    return plan.model_copy(update={"required_evidence_ids": required_ids})


# 5. Cascade default --------------------------------------------------------


def test_cascade_is_on_by_default() -> None:
    engine = RetrievalEngine(MemoryRepository([]))

    assert engine._enable_dense_escalation is True


def test_cascade_can_still_be_turned_off_explicitly() -> None:
    engine = RetrievalEngine(MemoryRepository([]), enable_dense_escalation=False)

    assert engine._enable_dense_escalation is False


async def test_default_construction_reports_the_cascade_as_enabled() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    engine = RetrievalEngine(MemoryRepository([]))

    assert engine._enable_dense_escalation is True
    assert await engine.retrieve(make_query(user_id, organization_id)) == []


async def test_non_cascade_path_populates_mentioned_entities() -> None:
    """The default path must report the coverage the sufficiency gate reads.

    With the cascade on, `_fuse_and_score` on the primary pass fills
    `mentioned_entities`. The opt-out path used to pass no `entity_names` at all,
    so every result there claimed to mention nothing -- and any gate that read
    it would escalate on a query that had already been answered.
    """
    user_id = uuid4()
    organization_id = uuid4()
    memory = make_memory(
        user_id=user_id,
        organization_id=organization_id,
        title="Gina started a business",
        content="Gina started a business",
        embedding=[1.0, 0.0],
    )
    engine = RetrievalEngine(
        MemoryRepository([memory]),
        enable_dense_escalation=False,
    )

    results = await engine.retrieve(
        make_query(user_id, organization_id, text="What do Jon and Gina have in common?"),
        query_embedding=[1.0, 0.0],
    )

    assert results
    assert all(result.mentioned_entities for result in results)
    assert "gina" in results[0].mentioned_entities

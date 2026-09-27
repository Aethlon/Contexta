from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from pytest import approx
from sqlalchemy.dialects import postgresql

from contexta.core.retrieval.fusion import weighted_reciprocal_rank_fusion
from contexta.models.memory import MemoryRecord
from contexta.repositories.memory_repo import MemoryRepository


def make_fusion_memory(utility_score: float = 0.0) -> MemoryRecord:
    return MemoryRecord(
        id=uuid4(),
        user_id=uuid4(),
        organization_id=uuid4(),
        memory_type="project",
        title="Contexta",
        content="Python retrieval",
        source_type="user_explicit",
        confidence=1.0,
        importance=0.5,
        utility_score=utility_score,
        embedding=[1.0, 0.0],
        memory_state="active",
        is_archived=False,
        valid_to=None,
        created_at=datetime.now(UTC),
    )


def test_weighted_rrf_rewards_consistent_cross_channel_rankings() -> None:
    first = make_fusion_memory()
    second = make_fusion_memory()

    fused = weighted_reciprocal_rank_fusion(
        {
            "dense": [first, second],
            "lexical": [second, first],
            "graph": [first],
        },
        weights={"dense": 0.6, "lexical": 0.3, "graph": 0.1},
    )

    assert fused[0].memory.id == first.id
    assert fused[0].score > fused[1].score
    assert dict(fused[0].channel_ranks) == {"dense": 1, "lexical": 2, "graph": 1}


def test_rrf_uses_utility_only_as_a_small_prior() -> None:
    low_utility = make_fusion_memory(-1.0)
    high_utility = make_fusion_memory(1.0)

    fused = weighted_reciprocal_rank_fusion(
        {
            "dense": [low_utility],
            "graph": [high_utility],
        },
        weights={"dense": 0.5, "graph": 0.5},
    )

    assert fused[0].memory.id == high_utility.id
    assert fused[0].score - fused[1].score == approx(0.005)


async def test_lexical_repository_uses_parameterized_tsvector_ranking() -> None:
    organization_id = uuid4()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session = AsyncMock()
    session.execute.return_value = result
    repository = MemoryRepository(session, tenant_id=organization_id)

    assert await repository.get_by_lexical_similarity(
        uuid4(),
        "python contexta",
        limit=25,
    ) == []
    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled).lower()
    bound = {str(value) for value in compiled.params.values()}

    assert "websearch_to_tsquery" in sql
    assert "ts_rank_cd" in sql
    assert "memory_record.organization_id" in sql
    assert "limit" in sql

    # Every user-supplied token must reach Postgres as a bound parameter, never as
    # SQL text. Both the raw query and the sanitised tsquery text are checked so the
    # assertion cannot pass by accident.
    assert "python contexta" not in sql
    assert "python" not in sql
    assert "contexta" not in sql

    # The bound tsquery is the stopword-filtered, OR-joined multi-term form: a
    # single plain phrase would silently drop every other matching term.
    assert "python OR contexta" in bound
    assert "english" in bound

    # 32 is RANK_NORM_RDIVRPLUSONE. It is part of the ranking contract, so it must
    # stay a bound parameter too.
    assert 32 in compiled.params.values()

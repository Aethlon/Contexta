"""Tests for advanced core features: Procedural memory, Feedback loop, and Batch retrieval."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from contexta.api.app import app
from contexta.core.context.builder import ContextBuilder
from contexta.core.decay.engine import DecayEngine
from contexta.core.schemas import ContextConfig, ContextRequest, RetrievalQuery
from contexta.core.types import MemoryState, MemoryType
from contexta.db import get_db_session
from contexta.models.memory import MemoryRecord


@pytest.fixture(autouse=True)
def override_db():
    mock_session = AsyncMock()

    async def _override():
        yield mock_session

    app.dependency_overrides[get_db_session] = _override
    yield
    app.dependency_overrides.pop(get_db_session, None)


def test_procedural_memory_decay_exemption():
    """Verify that procedural and rule memories are permanently exempt from decay."""
    decay_engine = DecayEngine()
    old_time = datetime.now(UTC) - timedelta(days=365)  # 1 year old

    rule_mem = MemoryRecord(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        memory_type=MemoryType.PROCEDURAL.value,
        title="Coding rule",
        content="Always write async functions with type annotations",
        memory_state=MemoryState.ACTIVE.value,
        is_pinned=False,
        created_at=old_time,
        updated_at=old_time,
    )

    state = decay_engine.transition_for(rule_mem)
    assert state == MemoryState.ACTIVE.value, "Procedural memory must remain ACTIVE regardless of age"

    rule_mem2 = MemoryRecord(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        memory_type=MemoryType.RULE.value,
        title="Safety directive",
        content="Never drop production databases",
        memory_state=MemoryState.ACTIVE.value,
        is_pinned=False,
        created_at=old_time,
        updated_at=old_time,
    )

    state2 = decay_engine.transition_for(rule_mem2)
    assert state2 == MemoryState.ACTIVE.value, "Rule memory must remain ACTIVE regardless of age"


def test_context_builder_rules_segregation():
    """Verify that ContextBuilder segregates procedural rules from standard facts."""
    builder = ContextBuilder()
    u_id = uuid.uuid4()
    org_id = uuid.uuid4()

    memories = [
        MemoryRecord(
            id=uuid.uuid4(),
            user_id=u_id,
            organization_id=org_id,
            memory_type=MemoryType.RULE.value,
            title="Formatting Directive",
            content="Format dates as YYYY-MM-DD",
            importance=0.9,
            is_archived=False,
        ),
        MemoryRecord(
            id=uuid.uuid4(),
            user_id=u_id,
            organization_id=org_id,
            memory_type=MemoryType.PREFERENCE.value,
            title="Editor",
            content="User uses Neovim",
            importance=0.8,
            is_archived=False,
        ),
    ]

    req = ContextRequest(
        user_id=u_id,
        organization_id=org_id,
        session_id=uuid.uuid4(),
        config=ContextConfig(),
    )

    built = builder.build(req, memories)
    assert len(built.rules) == 1
    assert built.rules[0]["content"] == "Format dates as YYYY-MM-DD"
    assert len(built.preferences) == 1
    assert built.preferences[0]["content"] == "User uses Neovim"


@pytest.mark.asyncio
async def test_batch_get_memories_endpoint():
    """Test POST /v1/memories/batch-get for concurrent multi-memory fetching."""
    m_id1 = uuid.uuid4()
    m_id2 = uuid.uuid4()
    u_id = uuid.uuid4()
    org_id = uuid.uuid4()

    fake_records = [
        MemoryRecord(
            id=m_id1,
            user_id=u_id,
            organization_id=org_id,
            memory_type="fact",
            title="Fact 1",
            content="Content 1",
            importance=0.8,
            confidence=0.9,
            utility_score=0.0,
            tags=["tag1"],
            memory_state="active",
            is_pinned=False,
            is_archived=False,
            created_at=datetime.now(UTC),
        ),
        MemoryRecord(
            id=m_id2,
            user_id=u_id,
            organization_id=org_id,
            memory_type="preference",
            title="Pref 2",
            content="Content 2",
            importance=0.7,
            confidence=0.85,
            utility_score=0.2,
            tags=["tag2"],
            memory_state="active",
            is_pinned=True,
            is_archived=False,
            created_at=datetime.now(UTC),
        ),
    ]

    with patch("contexta.repositories.memory_repo.MemoryRepository.get_many_by_ids", new=AsyncMock(return_value=fake_records)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post(
                "/v1/memories/batch-get",
                json={"memory_ids": [str(m_id1), str(m_id2)]},
                headers={
                    "x-organization-id": str(org_id),
                    "x-user-id": str(u_id),
                },
            )
            assert res.status_code == 200
            data = res.json()
            assert data["count"] == 2
            assert len(data["memories"]) == 2
            assert data["memories"][0]["id"] == str(m_id1)
            assert data["memories"][1]["id"] == str(m_id2)


@pytest.mark.asyncio
async def test_memory_feedback_endpoint():
    """Test POST /v1/memories/{id}/feedback for active reinforcement."""
    m_id = uuid.uuid4()
    u_id = uuid.uuid4()
    org_id = uuid.uuid4()

    fake_record = MemoryRecord(
        id=m_id,
        user_id=u_id,
        organization_id=org_id,
        memory_type="fact",
        title="Fact 1",
        content="Content 1",
        importance=0.8,
        confidence=0.9,
        utility_score=0.25,
        memory_state="active",
    )

    with patch("contexta.repositories.memory_repo.MemoryRepository.apply_feedback", new=AsyncMock(return_value=fake_record)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post(
                f"/v1/memories/{m_id}/feedback",
                json={"signal": "positive", "penalty": 0.5},
                headers={
                    "x-organization-id": str(org_id),
                    "x-user-id": str(u_id),
                },
            )
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "success"
            assert data["memory_id"] == str(m_id)
            assert data["utility_score"] == 0.25


@pytest.mark.asyncio
async def test_batch_retrieval_endpoint():
    """Test POST /v1/retrieve/batch for parallel multi-query retrieval."""
    u_id = uuid.uuid4()
    org_id = uuid.uuid4()

    mock_engine = AsyncMock()
    mock_engine.retrieve = AsyncMock(return_value=[])

    with patch("contexta.api.routes.retrieval.RetrievalEngine", return_value=mock_engine), \
         patch("contexta.services.embedding.EmbeddingService.embed_text", new=AsyncMock(return_value=[0.1] * 1536)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post(
                "/v1/retrieve/batch",
                json={
                    "queries": [
                        {"query_text": "What is the project architecture?", "user_id": str(u_id), "organization_id": str(org_id)},
                        {"query_text": "What are user preferences?", "user_id": str(u_id), "organization_id": str(org_id)},
                    ]
                },
                headers={
                    "x-organization-id": str(org_id),
                    "x-user-id": str(u_id),
                },
            )
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "success"
            assert data["count"] == 2
            assert len(data["batch_results"]) == 2
            assert data["batch_results"][0]["query"] == "What is the project architecture?"
            assert data["batch_results"][1]["query"] == "What are user preferences?"

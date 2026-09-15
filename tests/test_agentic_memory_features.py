"""Tests for Level 7 & 8 Agentic Memory features:
- AgenticRetrievalEngine (multi-hop investigative search)
- ReflectionEngine (autonomous consolidation, contradiction detection, pattern discovery)
- ContextBuilder (Dynamic Context Engineering: to_system_prompt and to_xml)
- Endpoints: POST /v1/retrieve/investigate and POST /v1/memories/reflect
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from contexta.api.app import app
from contexta.core.context.builder import ContextBuilder
from contexta.core.reflection.engine import ReflectionEngine
from contexta.core.retrieval.agentic_engine import AgenticRetrievalEngine
from contexta.core.retrieval.engine import RetrievalEngine, RetrievalResult
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


@pytest.mark.asyncio
async def test_agentic_retrieval_investigative_loop():
    """Verify that AgenticRetrievalEngine performs multi-hop investigation across connected entities."""
    u_id = uuid.uuid4()
    org_id = uuid.uuid4()

    mock_engine = AsyncMock(spec=RetrievalEngine)
    m1 = MemoryRecord(
        id=uuid.uuid4(),
        user_id=u_id,
        organization_id=org_id,
        title="Migrated to React",
        content="Migrated frontend stack from Vue to React in 2023.",
        memory_type="event",
        tags=["frontend", "vue", "react"],
        created_at=datetime.now(UTC),
    )
    r1 = RetrievalResult(
        memory=m1,
        score=0.92,
        semantic_score=0.90,
        graph_score=0.1,
        importance_score=0.8,
        recency_score=0.9,
        keyword_score=0.85,
    )

    m2 = MemoryRecord(
        id=uuid.uuid4(),
        user_id=u_id,
        organization_id=org_id,
        title="Legacy Vue Setup",
        content="Used Vue with Vuex for state management.",
        memory_type="fact",
        tags=["vue", "frontend"],
        created_at=datetime.now(UTC) - timedelta(days=400),
    )
    r2 = RetrievalResult(
        memory=m2,
        score=0.85,
        semantic_score=0.80,
        graph_score=0.2,
        importance_score=0.7,
        recency_score=0.5,
        keyword_score=0.8,
    )

    # First call returns r1 (seed), second call (sub-query for 'vue') returns r2, third returns empty
    mock_engine.retrieve = AsyncMock(side_effect=[[r1], [r2], []])

    agentic = AgenticRetrievalEngine(retrieval_engine=mock_engine)
    result = await agentic.investigate(
        query_text="What frontend stack did we use before switching to React?",
        user_id=u_id,
        organization_id=org_id,
        max_hops=2,
    )

    assert result.query == "What frontend stack did we use before switching to React?"
    assert len(result.memories) == 2
    assert len(result.investigation_trace) >= 2
    assert "vue" in result.entities_discovered
    assert "<memory_investigation" in result.synthesized_context
    assert "<investigation_trace>" in result.synthesized_context
    assert "<verified_evidence>" in result.synthesized_context


def test_reflection_contradiction_detection():
    """Verify that ReflectionEngine detects contradiction transitions between older and newer facts."""
    reflection = ReflectionEngine()
    u_id = uuid.uuid4()
    org_id = uuid.uuid4()

    older = MemoryRecord(
        id=uuid.uuid4(),
        user_id=u_id,
        organization_id=org_id,
        title="City",
        content="User lives in San Francisco",
        tags=["location"],
        created_at=datetime.now(UTC) - timedelta(days=100),
    )
    newer = MemoryRecord(
        id=uuid.uuid4(),
        user_id=u_id,
        organization_id=org_id,
        title="Relocation",
        content="User moved to New York last month",
        tags=["location"],
        created_at=datetime.now(UTC),
    )

    contradictions = reflection.detect_contradictions([older, newer])
    assert len(contradictions) == 1
    c_older, c_newer, reason = contradictions[0]
    assert c_older.id == older.id
    assert c_newer.id == newer.id
    assert "Transition marker" in reason


def test_reflection_pattern_consolidation():
    """Verify that ReflectionEngine extracts recurring patterns into PATTERN memories."""
    reflection = ReflectionEngine()
    u_id = uuid.uuid4()
    org_id = uuid.uuid4()

    memories = [
        MemoryRecord(id=uuid.uuid4(), user_id=u_id, organization_id=org_id, content="Session 1 using Rust", tags=["rust"]),
        MemoryRecord(id=uuid.uuid4(), user_id=u_id, organization_id=org_id, content="Session 2 compiling Rust", tags=["rust"]),
        MemoryRecord(id=uuid.uuid4(), user_id=u_id, organization_id=org_id, content="Session 3 debugging Rust", tags=["rust"]),
    ]

    patterns = reflection.consolidate_patterns(memories, user_id=u_id, organization_id=org_id, min_occurrences=3)
    assert len(patterns) == 1
    assert patterns[0].memory_type == MemoryType.PATTERN.value
    assert "rust" in patterns[0].tags
    assert "Recurring Affinity: Rust" in patterns[0].title


def test_dynamic_context_engineering_formats():
    """Verify that ContextBuilder formats system prompts into both Markdown and structured XML."""
    builder = ContextBuilder()
    u_id = uuid.uuid4()
    org_id = uuid.uuid4()

    memories = [
        MemoryRecord(
            id=uuid.uuid4(),
            user_id=u_id,
            organization_id=org_id,
            memory_type=MemoryType.RULE.value,
            title="Style Guide",
            content="Never use var, always use const/let",
            importance=0.95,
        ),
        MemoryRecord(
            id=uuid.uuid4(),
            user_id=u_id,
            organization_id=org_id,
            memory_type=MemoryType.PREFERENCE.value,
            title="Theme",
            content="Dark mode enthusiast",
            importance=0.8,
        ),
    ]

    req = ContextRequest(user_id=u_id, organization_id=org_id, session_id=uuid.uuid4(), config=ContextConfig())
    built = builder.build(req, memories)

    # 1. Test Markdown System Prompt
    md_prompt = builder.to_system_prompt(built, format="markdown")
    assert "## Operating Rules & Behavioral Directives" in md_prompt
    assert "- **Style Guide**: Never use var, always use const/let" in md_prompt
    assert "## User Profile & Preferences" in md_prompt
    assert "- Dark mode enthusiast" in md_prompt

    # 2. Test XML System Prompt
    xml_prompt = builder.to_system_prompt(built, format="xml")
    assert "<agent_context>" in xml_prompt
    assert "<operating_rules>" in xml_prompt
    assert "<rule title=\"Style Guide\">Never use var, always use const/let</rule>" in xml_prompt
    assert "<user_preferences>" in xml_prompt
    assert "<preference>Dark mode enthusiast</preference>" in xml_prompt


@pytest.mark.asyncio
async def test_investigate_endpoint():
    """Test POST /v1/retrieve/investigate endpoint."""
    u_id = uuid.uuid4()
    org_id = uuid.uuid4()

    mock_agentic = AsyncMock()
    mock_agentic.investigate = AsyncMock(
        return_value=AsyncMock(
            query="test",
            execution_time_ms=12.5,
            entities_discovered=["react", "vue"],
            investigation_trace=[],
            temporal_evolution=[],
            synthesized_context="<test/>",
            memories=[],
        )
    )

    with patch("contexta.api.routes.retrieval.AgenticRetrievalEngine", return_value=mock_agentic), \
         patch("contexta.services.embedding.EmbeddingService.embed_text", new=AsyncMock(return_value=[0.1] * 1536)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post(
                "/v1/retrieve/investigate",
                json={"query_text": "What stack did we use?", "user_id": str(u_id), "max_hops": 2},
                headers={"x-organization-id": str(org_id), "x-user-id": str(u_id)},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "success"
            assert data["query"] == "test"
            assert data["execution_time_ms"] == 12.5


@pytest.mark.asyncio
async def test_reflect_endpoint():
    """Test POST /v1/memories/reflect endpoint."""
    u_id = uuid.uuid4()
    org_id = uuid.uuid4()

    with patch("contexta.repositories.memory_repo.MemoryRepository.get_by_user", new=AsyncMock(return_value=[])):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post(
                "/v1/memories/reflect",
                json={"user_id": str(u_id), "apply_supersession": True},
                headers={"x-organization-id": str(org_id), "x-user-id": str(u_id)},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "success"
            assert data["user_id"] == str(u_id)
            assert data["contradictions_resolved"] == 0

"""Unit tests for Contexta Cortex (JEV Decision & Routing Layer)."""

from __future__ import annotations

from datetime import UTC, datetime
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from contexta.config.settings import Settings
from contexta.core.cortex.client import JevClient
from contexta.core.cortex.decisions import (
    CortexReadDecision,
    CortexTelemetry,
    CortexWriteDecision,
)
from contexta.core.cortex.engine import ContextaCortex
from contexta.core.pipeline import FastMemoryOrchestrator
from contexta.core.schemas import ExtractedMemory, ObservationPayload, RetrievalQuery
from contexta.core.types import MemoryType, SourceType


# ── 1. RAW RESPONSE PARSING & RESILIENCE TESTS ──────────────────────────

def test_cortex_write_decision_from_valid_jev_response():
    """Verify standard JEV choice, score, and noul answers parse cleanly."""
    raw_data = {
        "model": "jev-latest",
        "id": "req-12345",
        "answers": {
            "should_store": {"noul": 0.96},
            "memory_type": {"choice": "preference"},
            "importance": {"score": 8.5},
            "is_update": {"noul": 0.82},
            "needs_temporal": {"noul": 0.15},
            "needs_entity_rel": {"noul": 0.70},
            "extraction_depth": {"choice": "deep"},
        },
    }
    telemetry = CortexTelemetry(latency_ms=145.2, source="jev", jev_request_id="req-12345")
    decision = CortexWriteDecision.from_jev_response(raw_data, telemetry)

    assert decision.should_store is True
    assert decision.store_probability == 0.96
    assert decision.suggested_memory_type == "preference"
    assert decision.importance_score == 0.85  # Normalized from 8.5 / 10
    assert decision.is_update is True
    assert decision.needs_temporal is False
    assert decision.needs_entity_rel is True
    assert decision.extraction_depth == "deep"
    assert "store=True" in decision.derived_summary
    assert decision.telemetry.latency_ms == 145.2
    assert decision.telemetry.jev_request_id == "req-12345"


def test_cortex_write_decision_with_alternate_field_names():
    """Verify parser resilience when JEV uses alternate probability/value keys."""
    raw_data = {
        "model": "jev-latest",
        "answers": {
            "should_store": {"probability": 0.35},
            "memory_type": {"selected": "DECISION"},
            "importance": {"value": 4.0},
            "is_update": 0.1,  # Raw float
            "needs_temporal": True,  # Raw boolean
            "needs_entity_rel": {"choice": "yes"},  # Choice-based boolean
            "extraction_depth": "normal",
        },
    }
    telemetry = CortexTelemetry(latency_ms=80.0, source="jev")
    decision = CortexWriteDecision.from_jev_response(raw_data, telemetry)

    assert decision.should_store is False  # 0.35 < 0.5
    assert decision.store_probability == 0.35
    assert decision.suggested_memory_type == "decision"
    assert decision.importance_score == 0.4
    assert decision.is_update is False
    assert decision.needs_temporal is True
    assert decision.needs_entity_rel is True
    assert decision.extraction_depth == "normal"


def test_cortex_write_decision_with_missing_and_malformed_answers():
    """Verify parser never crashes on empty, null, or malformed JEV answers."""
    # Test None payload
    telemetry = CortexTelemetry(latency_ms=10.0, source="heuristic_fallback")
    d1 = CortexWriteDecision.from_jev_response(None, telemetry)
    assert d1.should_store is True  # Safe default
    assert d1.suggested_memory_type == "fact"

    # Test empty dict
    d2 = CortexWriteDecision.from_jev_response({}, telemetry)
    assert d2.should_store is True
    assert d2.importance_score == 0.5

    # Test missing answers dictionary
    d3 = CortexWriteDecision.from_jev_response({"error": "some internal error"}, telemetry)
    assert d3.should_store is True

    # Test unexpected choice option
    d4 = CortexWriteDecision.from_jev_response(
        {
            "answers": {
                "memory_type": {"choice": "completely_unknown_category"},
                "importance": {"score": "not-a-number"},
            }
        },
        telemetry,
    )
    assert d4.suggested_memory_type == "fact"  # Graceful fallback to fact
    assert d4.importance_score == 0.5  # Graceful fallback to 0.5


def test_cortex_read_decision_parsing():
    """Verify retrieval routing decision parser handles valid, partial, and malformed inputs."""
    raw_data = {
        "answers": {
            "retrieval_strategy": {"choice": "exact"},
            "requires_graph": {"noul": 0.1},
            "requires_temporal_filter": {"noul": 0.8},
            "priority_memory_type": {"choice": "rule"},
        }
    }
    telemetry = CortexTelemetry(latency_ms=95.0, source="jev")
    decision = CortexReadDecision.from_jev_response(raw_data, telemetry)

    assert decision.strategy == "exact"
    assert decision.requires_graph is False
    assert decision.requires_temporal_filter is True
    assert decision.priority_memory_type == "rule"

    # Unexpected strategy defaults to hybrid
    bad_data = {"answers": {"retrieval_strategy": {"choice": "random_unsupported"}}}
    bad_dec = CortexReadDecision.from_jev_response(bad_data, telemetry)
    assert bad_dec.strategy == "hybrid"


# ── 2. ENGINE HEURISTIC FALLBACK TESTS ──────────────────────────────────

@pytest.mark.asyncio
async def test_cortex_write_heuristic_fallback():
    """Verify local heuristic accurately categorizes memories when offline/fallback."""
    settings = Settings(feature_cortex=True, jev_api_key="")
    cortex = ContextaCortex(settings=settings)

    # 1. Ephemeral greeting -> candidate skip
    payload_greeting = ObservationPayload(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        messages=[{"role": "user", "text": "hey hello there!"}],
    )
    dec_greeting = await cortex.evaluate_observation(payload_greeting)
    assert dec_greeting.should_store is False
    assert dec_greeting.telemetry.source == "heuristic_fallback"

    # 2. Preference statement
    payload_pref = ObservationPayload(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        messages=[{"role": "user", "text": "I really prefer TypeScript with FastAPI over Django."}],
    )
    dec_pref = await cortex.evaluate_observation(payload_pref)
    assert dec_pref.should_store is True
    assert dec_pref.suggested_memory_type == "preference"
    assert dec_pref.importance_score >= 0.7

    # 3. Decision statement with update indicator
    payload_dec = ObservationPayload(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        messages=[{"role": "user", "text": "We decided to switch to pgvector instead of Pinecone."}],
    )
    dec_dec = await cortex.evaluate_observation(payload_dec)
    assert dec_dec.should_store is True
    assert dec_dec.suggested_memory_type == "decision"
    assert dec_dec.is_update is True


@pytest.mark.asyncio
async def test_cortex_read_heuristic_fallback():
    """Verify local heuristic accurately classifies query intent."""
    settings = Settings(feature_cortex=True, jev_api_key="")
    cortex = ContextaCortex(settings=settings)

    # Exact token / code
    q_exact = RetrievalQuery(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        query_text="What was the error code 'ERR_502_BAD_GATEWAY'?",
    )
    dec_exact = await cortex.classify_query(q_exact)
    assert dec_exact.strategy == "exact"

    # Graph relationship query
    q_graph = RetrievalQuery(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        query_text="Who is leading the backend team and works with Sarah?",
    )
    dec_graph = await cortex.classify_query(q_graph)
    assert dec_graph.strategy == "graph"
    assert dec_graph.requires_graph is True

    # Temporal query
    q_temp = RetrievalQuery(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        query_text="When did we deploy the auth service last week?",
    )
    dec_temp = await cortex.classify_query(q_temp)
    assert dec_temp.strategy == "temporal"
    assert dec_temp.requires_temporal_filter is True


# ── 3. FEATURE FLAG & SHORT-CIRCUIT TESTS ───────────────────────────────

@pytest.mark.asyncio
async def test_cortex_feature_flag_disabled():
    """Verify that when feature_cortex is False, Cortex immediately returns disabled pass-through."""
    settings = Settings(feature_cortex=False)
    cortex = ContextaCortex(settings=settings)

    payload = ObservationPayload(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        messages=[{"role": "user", "text": "Hello there"}],
    )
    dec = await cortex.evaluate_observation(payload)
    assert dec.should_store is True  # Pass-through
    assert dec.telemetry.source == "disabled"

    query = RetrievalQuery(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        query_text="Find my preferences",
    )
    r_dec = await cortex.classify_query(query)
    assert r_dec.strategy == "hybrid"
    assert r_dec.telemetry.source == "disabled"


@pytest.mark.asyncio
async def test_fast_memory_orchestrator_candidate_skip():
    """Verify that should_store=False triggers early candidate skip, saving LLM extraction."""
    mock_cortex = MagicMock()
    mock_cortex.is_enabled = True
    # Simulate Cortex deciding this observation is trivial chit-chat
    mock_cortex.evaluate_observation = AsyncMock(
        return_value=CortexWriteDecision(
            should_store=False,
            store_probability=0.1,
            derived_summary="Cortex skip: Trivial greeting",
            telemetry=CortexTelemetry(latency_ms=12.5, source="jev"),
        )
    )

    mock_extractor = MagicMock()
    mock_extractor.extract = AsyncMock(return_value=[])

    orchestrator = FastMemoryOrchestrator(
        cortex=mock_cortex,
        extraction_worker=mock_extractor,
    )

    payload = ObservationPayload(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        messages=[{"role": "user", "text": "hey thanks"}],
    )

    session = AsyncMock()
    result = await orchestrator.orchestrate(payload, session)

    assert result.discarded_count == 1
    assert result.extracted_count == 0
    assert result.stored_count == 0
    assert len(result.details) == 1
    assert result.details[0]["action"] == "candidate_skip"
    assert result.details[0]["summary"] == "Cortex skip: Trivial greeting"
    # Verify extractor was NEVER called, proving LLM extraction was skipped!
    mock_extractor.extract.assert_not_called()


@pytest.mark.asyncio
async def test_fast_memory_orchestrator_configurable_skip_gate():
    """Verify that if cortex_early_skip_enabled=False, pipeline proceeds even if should_store=False."""
    mock_cortex = MagicMock()
    mock_cortex.is_enabled = True
    mock_cortex.evaluate_observation = AsyncMock(
        return_value=CortexWriteDecision(
            should_store=False,
            store_probability=0.2,
            derived_summary="Cortex advisory skip",
            telemetry=CortexTelemetry(latency_ms=10.0, source="jev"),
        )
    )

    # Extractor returns a memory independently
    sample_memory = ExtractedMemory(
        memory_type=MemoryType.FACT,
        source_type=SourceType.USER_EXPLICIT,
        title="Server Port",
        content="The server runs on port 8080.",
    )
    mock_extractor = MagicMock()
    mock_extractor.extract = AsyncMock(return_value=[sample_memory])

    orchestrator = FastMemoryOrchestrator(
        cortex=mock_cortex,
        extraction_worker=mock_extractor,
    )

    payload = ObservationPayload(
        user_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        messages=[{"role": "user", "text": "The server runs on port 8080"}],
    )

    session = AsyncMock()
    mock_exec_res = MagicMock()
    mock_exec_res.scalars.return_value.all.return_value = []
    mock_exec_res.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_exec_res)

    # Disable early skip via settings patch and mock background embedding task
    with patch("contexta.core.pipeline.get_settings") as mock_settings, \
         patch("contexta.core.pipeline.enqueue_embedding_generation"):
        mock_settings.return_value.cortex_early_skip_enabled = False
        result = await orchestrator.orchestrate(payload, session)

        # Extractor WAS called because early skip was disabled
        mock_extractor.extract.assert_called_once()
        assert result.extracted_count == 1


@pytest.mark.asyncio
async def test_retrieval_engine_with_cortex_routing():
    """Verify RetrievalEngine classifies query via Cortex and adapts layer scoring."""
    from contexta.core.retrieval.engine import RetrievalEngine
    from contexta.models.memory import MemoryRecord

    u_id = uuid.uuid4()
    org_id = uuid.uuid4()

    mem1 = MemoryRecord(
        id=uuid.uuid4(),
        user_id=u_id,
        organization_id=org_id,
        memory_type="fact",
        title="PostgreSQL",
        content="PostgreSQL database configuration",
        importance=0.8,
        memory_state="active",
        is_archived=False,
        created_at=datetime.now(UTC),
    )

    fake_mem_repo = MagicMock()
    fake_mem_repo.get_by_user = AsyncMock(return_value=[mem1])

    mock_cortex = MagicMock()
    mock_cortex.is_enabled = True
    mock_cortex.classify_query = AsyncMock(
        return_value=CortexReadDecision(
            strategy="exact",
            requires_graph=False,
            requires_temporal_filter=False,
            priority_memory_type="fact",
            derived_summary="Cortex exact routing",
            telemetry=CortexTelemetry(latency_ms=45.0, source="jev"),
        )
    )

    engine = RetrievalEngine(
        memory_repository=fake_mem_repo,
        cortex=mock_cortex,
    )

    query = RetrievalQuery(
        user_id=u_id,
        organization_id=org_id,
        query_text="PostgreSQL configuration",
        limit=5,
    )

    results = await engine.retrieve(query)
    mock_cortex.classify_query.assert_called_once_with(query)
    assert len(results) == 1
    assert results[0].memory.id == mem1.id
    assert results[0].score > 0.0

"""Retrieval-response observability: bitemporal fields, fact identity, channel diagnostics.

Retrieval used to emit `created_at` and nothing else, which made three questions
unanswerable from a response: when a belief became true, whether the row was
still open, and which retrieval channels actually contributed. These tests pin the
additive shape, the backwards-compatibility guard (the old key set must stay a
subset of the new one), and the rule that an unavailable channel count is
reported as `null` rather than invented.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from contexta.api.app import app
from contexta.api.routes.retrieval import (
    _channel_diagnostics,
    _serialize_result,
)
from contexta.core.retrieval.engine import CascadeEscalation, RetrievalResult
from contexta.core.retrieval.fusion import SufficiencyAssessment
from contexta.db import get_db_session
from contexta.models.memory import MemoryRecord

NEW_MEMORY_KEYS = frozenset(
    {
        "valid_from",
        "valid_to",
        "event_at",
        "observed_at",
        "temporal_precision",
        "temporal_basis",
        "fact_key",
        "last_accessed_at",
        "is_current",
    }
)
# The key set `_serialize_result` emitted before this change. Backwards
# compatibility is "the old keys are a SUBSET of the new keys": nothing may be
# removed or renamed, and clients may depend on the current shape.
LEGACY_MEMORY_KEYS = frozenset(
    {
        "id",
        "user_id",
        "organization_id",
        "memory_type",
        "title",
        "content",
        "structured_data",
        "tags",
        "is_pinned",
        "is_archived",
        "memory_state",
        "created_at",
    }
)
LEGACY_RESULT_KEYS = frozenset(
    {
        "memory",
        "score",
        "semantic_score",
        "graph_score",
        "importance_score",
        "recency_score",
        "keyword_score",
    }
)
CHANNEL_KEYS = frozenset({"weights", "candidates", "unavailable_candidate_counts", "dense_escalation"})

# The model stores `valid_from`/`valid_to`/`last_accessed_at` as naive `DateTime`
# and `event_at`/`observed_at` as `TIMESTAMPTZ`, so the serialiser has to handle
# both kinds. One of each, deliberately.
NAIVE = datetime(2026, 3, 1, 12, 30, 45, 123456)  # noqa: DTZ001 - mirrors a naive column
AWARE = datetime(2026, 3, 1, 12, 30, 45, 123456, tzinfo=UTC)


def _memory(**overrides) -> MemoryRecord:
    """A real `MemoryRecord`, so the tests fail if a column name is wrong."""
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "organization_id": uuid.uuid4(),
        "memory_type": "fact",
        "title": "Fatima Okafor lives in Lisbon",
        "content": "Fatima Okafor lives in Lisbon, Portugal.",
        "structured_data": {"subject": "Fatima Okafor", "predicate": "lives_in", "object": "Lisbon"},
        "tags": ["profile"],
        "is_pinned": False,
        "is_archived": False,
        "memory_state": "active",
        "created_at": NAIVE,
        "updated_at": NAIVE,
        "valid_from": NAIVE,
        "valid_to": None,
        "event_at": AWARE,
        "observed_at": AWARE,
        "temporal_precision": "day",
        "temporal_basis": "explicit",
        "fact_key": "sfx1:" + "a" * 64,
        "last_accessed_at": NAIVE,
    }
    values.update(overrides)
    return MemoryRecord(**values)


def _result(memory: MemoryRecord, **overrides) -> RetrievalResult:
    values: dict[str, object] = {
        "memory": memory,
        "score": 0.91,
        "semantic_score": 0.8,
        "graph_score": 0.2,
        "importance_score": 0.5,
        "recency_score": 0.4,
        "keyword_score": 0.6,
    }
    values.update(overrides)
    return RetrievalResult(**values)


def _engine(escalation: object | None) -> object:
    """Stand-in for `RetrievalEngine` exposing only what the engine exposes."""
    engine = SimpleNamespace(last_escalation=escalation)
    engine._channel_weights = lambda _decision: {"dense": 0.5, "lexical": 0.3, "graph": 0.2}
    return engine


def _escalation(**overrides) -> CascadeEscalation:
    values: dict[str, object] = {
        "enabled": True,
        "escalated": False,
        "reason": "contract_satisfied",
        "dense_candidates": 0,
        "fused_candidates": 4,
        "assessment": SufficiencyAssessment(
            sufficient=True,
            reason="contract_satisfied",
            result_count=4,
            required_result_count=1,
            covered_entities=("Fatima Okafor",),
            required_entities=("Fatima Okafor",),
            missing_evidence_ids=(),
            top_score=0.91,
            runner_up_score=0.42,
            margin=0.49,
        ),
    }
    values.update(overrides)
    return CascadeEscalation(**values)


# ---------------------------------------------------------------------------
# Task 1: bitemporal and fact-identity fields
# ---------------------------------------------------------------------------


def test_serialize_result_emits_every_new_key():
    payload = _serialize_result(_result(_memory()))["memory"]

    assert NEW_MEMORY_KEYS <= set(payload), sorted(NEW_MEMORY_KEYS - set(payload))
    assert payload["valid_from"] == NAIVE.isoformat()
    assert payload["valid_to"] is None
    assert payload["event_at"] == AWARE.isoformat()
    assert payload["observed_at"] == AWARE.isoformat()
    assert payload["temporal_precision"] == "day"
    assert payload["temporal_basis"] == "explicit"
    assert payload["fact_key"].startswith("sfx1:")
    assert payload["last_accessed_at"] == NAIVE.isoformat()
    assert payload["is_current"] is True


def test_new_fields_present_when_every_underlying_value_is_null():
    memory = _memory(
        valid_from=None,
        valid_to=None,
        event_at=None,
        observed_at=None,
        temporal_precision=None,
        temporal_basis=None,
        fact_key=None,
        last_accessed_at=None,
    )
    payload = _serialize_result(_result(memory))["memory"]

    assert NEW_MEMORY_KEYS <= set(payload)
    for key in sorted(NEW_MEMORY_KEYS - {"is_current"}):
        assert key in payload, key
        assert payload[key] is None, key
    assert payload["is_current"] is True


def test_valid_from_is_emitted_even_though_it_is_non_null_in_the_schema():
    """`valid_from` is NOT NULL in the model; the response must carry it anyway.

    A caller debugging "when did this become true" has no other source for it:
    `created_at` is the ingestion time, not the belief time.
    """
    memory = _memory()
    assert memory.valid_from is not None
    payload = _serialize_result(_result(memory))["memory"]

    assert "valid_from" in payload
    assert payload["valid_from"] == memory.valid_from.isoformat()
    assert payload["valid_from"] != payload["created_at"] or memory.created_at == memory.valid_from


def test_valid_to_non_null_is_reflected_in_derived_is_current():
    superseded = _memory(valid_to=NAIVE + timedelta(days=1))
    payload = _serialize_result(_result(superseded))["memory"]

    assert payload["valid_to"] == (NAIVE + timedelta(days=1)).isoformat()
    assert payload["is_current"] is False

    current = _memory(valid_to=None)
    assert _serialize_result(_result(current))["memory"]["is_current"] is True


def test_superseded_pair_shares_one_fact_key_so_the_identity_is_debuggable():
    """Two rows for one fact slot must be distinguishable by `fact_key` alone."""
    closed = _memory(valid_to=NAIVE + timedelta(days=1), fact_key="sfx1:" + "b" * 64)
    replacement = _memory(fact_key=closed.fact_key)
    closed_payload = _serialize_result(_result(closed))["memory"]
    replacement_payload = _serialize_result(_result(replacement))["memory"]

    assert closed_payload["fact_key"] == replacement_payload["fact_key"]
    assert (closed_payload["valid_to"], closed_payload["is_current"]) == (
        closed.valid_to.isoformat(),
        False,
    )
    assert (replacement_payload["valid_to"], replacement_payload["is_current"]) == (None, True)


def test_legacy_key_set_is_a_subset_of_the_new_key_set():
    payload = _serialize_result(_result(_memory()))

    assert LEGACY_RESULT_KEYS <= set(payload), sorted(LEGACY_RESULT_KEYS - set(payload))
    assert LEGACY_MEMORY_KEYS <= set(payload["memory"]), sorted(
        LEGACY_MEMORY_KEYS - set(payload["memory"])
    )
    # Purely additive: the new keys are strictly a superset.
    assert set(payload["memory"]) > LEGACY_MEMORY_KEYS


def test_serialized_result_is_json_serialisable_with_no_datetime_or_uuid():
    # `structured_data` is a pre-existing raw JSONB passthrough, so it is modelled
    # with the plain JSON types the column can actually hold. Everything else in
    # the payload is built by this module and must be JSON-native.
    memory = _memory(
        structured_data={"subject": "Fatima Okafor", "spans": [1, 2], "flag": True},
        tags=["a", "b"],
    )
    payload = _serialize_result(_result(memory))

    def _assert_json_safe(value, path="memory"):
        if isinstance(value, dict):
            for key, item in value.items():
                assert isinstance(key, str), f"{path}.{key}"
                _assert_json_safe(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                _assert_json_safe(item, f"{path}[{index}]")
        else:
            assert value is None or isinstance(value, (str, int, float, bool)), (
                f"{path} leaked {type(value).__name__}: {value!r}"
            )

    _assert_json_safe(payload)
    # UUIDs are stringified, datetimes ISO-formatted, and the whole body round-trips.
    round_tripped = json.loads(json.dumps(payload))
    assert round_tripped["memory"]["fact_key"] == memory.fact_key
    assert round_tripped["memory"]["valid_from"] == memory.valid_from.isoformat()
    for key in sorted(NEW_MEMORY_KEYS):
        assert key in round_tripped["memory"], key


def test_naive_and_aware_datetimes_both_serialise_without_raising():
    naive = _serialize_result(_result(_memory()))["memory"]
    aware = _serialize_result(
        _result(_memory(valid_from=AWARE, valid_to=AWARE, last_accessed_at=AWARE, event_at=AWARE))
    )["memory"]

    assert "T" in naive["valid_from"] and "+" not in naive["valid_from"]
    assert naive["event_at"].endswith("+00:00")
    assert aware["valid_from"].endswith("+00:00")
    assert aware["valid_to"].endswith("+00:00")
    assert aware["event_at"] == aware["valid_from"]


def test_agentic_serialiser_emits_the_same_fields_and_keeps_is_current():
    """`/retrieve/investigate` uses its own serialiser; it must not lag behind."""
    from contexta.api.routes import retrieval as retrieval_route

    memory = _memory(valid_to=NAIVE + timedelta(days=2))
    item = _result(memory)
    payload = retrieval_route._memory_temporal_payload(item.memory)

    assert NEW_MEMORY_KEYS <= set(payload)
    assert payload["valid_to"] == (NAIVE + timedelta(days=2)).isoformat()
    assert payload["is_current"] is False
    assert json.loads(json.dumps(payload))["fact_key"] == memory.fact_key


# ---------------------------------------------------------------------------
# Task 2: channel diagnostics
# ---------------------------------------------------------------------------


def test_channel_diagnostics_reports_dense_count_and_nulls_for_untracked_channels():
    payload = _channel_diagnostics(_engine(_escalation()), returned_results=2)

    assert CHANNEL_KEYS <= set(payload)
    assert set(payload["candidates"]) == {"dense", "lexical", "graph"}
    assert payload["candidates"]["dense"] == 0
    # The engine now tracks every channel, so a real escalation record reports
    # all three rather than nulling the two it cannot see.
    assert payload["candidates"]["lexical"] == 0
    assert payload["candidates"]["graph"] == 0
    assert payload["unavailable_candidate_counts"] == []
    assert payload["weights"] == {"dense": 0.5, "lexical": 0.3, "graph": 0.2}
    assert payload["fused_candidates"] == 4
    assert payload["returned_results"] == 2
    assert payload["dense_escalation"]["enabled"] is True
    assert payload["dense_escalation"]["escalated"] is False
    assert payload["dense_escalation"]["reason"] == "contract_satisfied"
    assert payload["dense_escalation"]["sufficiency"]["sufficient"] is True
    assert payload["dense_escalation"]["sufficiency"]["margin"] == 0.49


def test_channel_diagnostics_reports_populated_non_dense_channel_counts():
    payload = _channel_diagnostics(
        _engine(
            _escalation(
                escalated=True,
                reason="missing_required_entity",
                dense_candidates=17,
                lexical_candidates=6,
                graph_candidates=11,
                fused_candidates=29,
            )
        ),
        returned_results=5,
    )

    assert payload["candidates"] == {"dense": 17, "lexical": 6, "graph": 11}
    assert payload["unavailable_candidate_counts"] == []
    assert payload["fused_candidates"] == 29
    assert payload["dense_escalation"]["escalated"] is True
    assert payload["dense_escalation"]["reason"] == "missing_required_entity"


def test_channel_diagnostics_reports_an_escalation_with_its_dense_count_and_reason():
    payload = _channel_diagnostics(
        _engine(
            _escalation(
                escalated=True,
                reason="evidence_missing",
                dense_candidates=17,
                fused_candidates=6,
                assessment=SufficiencyAssessment(
                    sufficient=False,
                    reason="evidence_missing",
                    result_count=1,
                    required_result_count=3,
                    covered_entities=(),
                    required_entities=("Fatima Okafor", "Lisbon"),
                    missing_evidence_ids=("mem-1",),
                ),
            )
        ),
        returned_results=6,
    )

    assert payload["candidates"]["dense"] == 17
    assert payload["dense_escalation"]["escalated"] is True
    assert payload["dense_escalation"]["reason"] == "evidence_missing"
    sufficiency = payload["dense_escalation"]["sufficiency"]
    assert sufficiency["sufficient"] is False
    assert sufficiency["missing_evidence_ids"] == ["mem-1"]
    assert sufficiency["required_entities"] == ["Fatima Okafor", "Lisbon"]
    assert sufficiency["covered_entities"] == []
    assert json.loads(json.dumps(payload))["fused_candidates"] == 6


def test_channel_diagnostics_is_present_when_the_engine_records_nothing():
    payload = _channel_diagnostics(_engine(None), returned_results=0)

    assert CHANNEL_KEYS <= set(payload)
    assert payload["candidates"] == {"dense": None, "lexical": None, "graph": None}
    assert payload["unavailable_candidate_counts"] == ["dense", "lexical", "graph"]
    assert payload["fused_candidates"] is None
    assert payload["dense_escalation"] == {
        "enabled": None,
        "escalated": None,
        "reason": None,
        "sufficiency": None,
    }
    json.dumps(payload)


def test_channel_diagnostics_degrades_to_nulls_instead_of_leaking_a_mock():
    """A test double (or any future non-conforming engine) must not leak objects."""
    payload = _channel_diagnostics(MagicMock(), returned_results=0)

    assert payload["candidates"] == {"dense": None, "lexical": None, "graph": None}
    # The mock answers every attribute with a `Mock`, so the resolver is
    # unusable and the engine class default is the only honest source left.
    assert payload["weights"] == {"dense": 0.5, "lexical": 0.3, "graph": 0.2}
    assert payload["fused_candidates"] is None
    assert payload["dense_escalation"]["enabled"] is None
    # A mock `assessment` still yields the full key set, every value `None`.
    assert set(payload["dense_escalation"]["sufficiency"].values()) == {None}
    json.dumps(payload)


def test_channel_diagnostics_nulls_everything_when_no_weights_are_reachable():
    """Even the weights must be `null`, not a Mock, when nothing exposes them."""
    with patch("contexta.api.routes.retrieval.RetrievalEngine", new=MagicMock()):
        payload = _channel_diagnostics(MagicMock(), returned_results=0)

    assert payload["weights"] is None
    assert payload["candidates"] == {"dense": None, "lexical": None, "graph": None}
    json.dumps(payload)


def test_channel_weights_fall_back_to_the_engine_class_defaults():
    engine = SimpleNamespace(last_escalation=_escalation(), _channel_weights=None)
    payload = _channel_diagnostics(engine, returned_results=1)

    assert payload["weights"] == {"dense": 0.5, "lexical": 0.3, "graph": 0.2}


def test_channel_weights_use_the_engines_own_boosted_values():
    engine = SimpleNamespace(
        last_escalation=_escalation(),
        _channel_weights=lambda _decision: {"dense": 0.7, "lexical": 0.3, "graph": 0.26},
    )
    payload = _channel_diagnostics(engine, returned_results=1)

    assert payload["weights"]["dense"] == 0.7


# ---------------------------------------------------------------------------
# Task 2 at the route boundary
# ---------------------------------------------------------------------------


@pytest.fixture
def override_db():
    """`conftest.py` already overrides `get_db_session`; keep a handle for clarity."""

    async def _override():
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _override
    yield
    app.dependency_overrides.clear()


async def _post(path: str, body: dict, org_id, user_id) -> dict:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            path,
            json=body,
            headers={
                "x-organization-id": str(org_id),
                "x-user-id": str(user_id),
                # ASGITransport hands back the compressed body undecompressed.
                "accept-encoding": "identity",
            },
        )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_retrieve_response_carries_a_channels_block_even_when_every_count_is_null(override_db):
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    engine = MagicMock()
    engine.retrieve = AsyncMock(return_value=[])
    engine.last_escalation = None

    with patch("contexta.api.routes.retrieval.RetrievalEngine", return_value=engine), patch(
        "contexta.services.embedding.EmbeddingService.embed_text",
        new=AsyncMock(return_value=[0.1] * 1024),
    ):
        body = await _post(
            "/v1/retrieve",
            {"query_text": "Where does Fatima Okafor live?", "user_id": str(user_id), "limit": 5},
            org_id,
            user_id,
        )

    assert body["status"] == "success"
    assert "channels" in body
    assert CHANNEL_KEYS <= set(body["channels"])
    assert body["channels"]["candidates"] == {"dense": None, "lexical": None, "graph": None}
    assert body["channels"]["weights"] is None
    assert body["channels"]["dense_escalation"]["escalated"] is None
    assert body["results"] == []
    json.dumps(body)


@pytest.mark.asyncio
async def test_retrieve_response_carries_populated_channels_and_temporal_fields(override_db):
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    memory = _memory(
        organization_id=org_id,
        user_id=user_id,
        memory_user_id=None,
        agent_id=None,
        project_id=None,
        session_id=None,
    )
    engine = MagicMock()
    engine.retrieve = AsyncMock(return_value=[_result(memory)])
    engine.last_escalation = _escalation(escalated=True, dense_candidates=11, fused_candidates=1)

    with patch("contexta.api.routes.retrieval.RetrievalEngine", return_value=engine), patch(
        "contexta.services.embedding.EmbeddingService.embed_text",
        new=AsyncMock(return_value=[0.1] * 1024),
    ):
        body = await _post(
            "/v1/retrieve",
            {"query_text": "Where does Fatima Okafor live?", "user_id": str(user_id), "limit": 5},
            org_id,
            user_id,
        )

    assert body["channels"]["candidates"]["dense"] == 11
    assert body["channels"]["dense_escalation"]["escalated"] is True
    assert body["channels"]["returned_results"] == 1
    assert len(body["results"]) == 1

    emitted = body["results"][0]["memory"]
    assert NEW_MEMORY_KEYS <= set(emitted)
    assert emitted["fact_key"] == memory.fact_key
    assert emitted["valid_from"] == memory.valid_from.isoformat()
    assert emitted["event_at"] == memory.event_at.isoformat()
    assert emitted["is_current"] is True
    assert emitted["temporal_precision"] == "day"


@pytest.mark.asyncio
async def test_batch_retrieve_shares_the_serialiser_and_the_channels_block(override_db):
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    engine = MagicMock()
    engine.retrieve = AsyncMock(return_value=[])
    engine.last_escalation = None

    with patch("contexta.api.routes.retrieval.RetrievalEngine", return_value=engine), patch(
        "contexta.services.embedding.EmbeddingService.embed_text",
        new=AsyncMock(return_value=[0.1] * 1024),
    ):
        body = await _post(
            "/v1/retrieve/batch",
            {
                "queries": [
                    {
                        "query_text": "Where does Fatima Okafor live?",
                        "user_id": str(user_id),
                        "organization_id": str(org_id),
                    },
                    {
                        "query_text": "What are the current project milestones?",
                        "user_id": str(user_id),
                        "organization_id": str(org_id),
                    },
                ]
            },
            org_id,
            user_id,
        )

    assert body["count"] == 2
    for entry in body["batch_results"]:
        assert CHANNEL_KEYS <= set(entry["channels"])
        assert entry["channels"]["candidates"] == {"dense": None, "lexical": None, "graph": None}
    json.dumps(body)

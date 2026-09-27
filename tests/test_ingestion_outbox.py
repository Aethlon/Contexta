from __future__ import annotations

import importlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from contexta.models.ingestion import (
    IngestionAttempt,
    IngestionDeadLetter,
    IngestionObservation,
    IngestionOutboxEvent,
    IngestionSourceTurn,
)
from contexta.repositories.ingestion_repo import IngestionRepository
from contexta.workers.outbox_tasks import _id_result


class _Bind:
    dialect = postgresql.dialect()


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        if isinstance(self.value, list):
            return self.value
        return [self.value]


class _Session:
    def __init__(self, result):
        self.result = result
        self.statement = None
        self.added = []
        self.flush_count = 0

    def get_bind(self):
        return _Bind()

    async def execute(self, statement):
        self.statement = statement
        return _Result(self.result)

    async def scalar(self, statement):
        self.scalar_statements = getattr(self, "scalar_statements", [])
        self.scalar_statements.append(statement)
        return 0

    def add(self, record):
        self.added.append(record)

    async def flush(self):
        self.flush_count += 1


def test_ingestion_models_register_expected_tables() -> None:
    assert IngestionObservation.__tablename__ == "ingestion_observation"
    assert IngestionSourceTurn.__tablename__ == "ingestion_source_turn"
    assert IngestionAttempt.__tablename__ == "ingestion_attempt"
    assert IngestionDeadLetter.__tablename__ == "ingestion_dead_letter"
    assert IngestionOutboxEvent.__tablename__ == "ingestion_outbox_event"
    assert IngestionObservation.__table__.c.payload.type.__class__.__name__ == "JSONB"
    assert IngestionObservation.__table__.c.organization_id.type.__class__.__name__ == "UUID"


async def test_idempotent_insert_accepts_metadata() -> None:
    tenant_id = uuid.uuid4()
    record = IngestionObservation(
        id=uuid.uuid4(),
        organization_id=tenant_id,
        user_id=uuid.uuid4(),
        idempotency_key="metadata-key",
        payload_hash="hash",
        payload={"messages": []},
        metadata_={"source": "test"},
        source="api",
        status="pending",
        attempt_count=0,
    )
    session = _Session(record)
    repository = IngestionRepository(session, tenant_id)

    inserted, created = await repository.insert_observation_idempotently(
        idempotency_key="metadata-key",
        user_id=record.user_id,
        session_id=None,
        payload={"messages": []},
        metadata={"source": "test"},
    )

    assert inserted is record
    assert created is True
    compiled = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "metadata" in compiled


def test_migration_follows_current_head() -> None:
    migration = importlib.import_module(
        "contexta.migrations.versions.20260923_0006_durable_ingestion_outbox"
    )
    assert migration.revision == "006"
    assert migration.down_revision == "005"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


async def test_claim_uses_postgresql_skip_locked() -> None:
    tenant_id = uuid.uuid4()
    observation = IngestionObservation(
        id=uuid.uuid4(),
        organization_id=tenant_id,
        user_id=uuid.uuid4(),
        idempotency_key="observation-key",
        payload_hash="hash",
        payload={"messages": []},
        source="api",
        status="pending",
        attempt_count=0,
        next_attempt_at=datetime.now(UTC),
    )
    session = _Session(observation)
    repository = IngestionRepository(session, tenant_id)

    attempt = await repository.claim_observation(observation.id, "worker-1")

    assert isinstance(attempt, IngestionAttempt)
    assert attempt.organization_id == tenant_id
    assert observation.status == "processing"
    compiled = str(
        session.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "FOR UPDATE" in compiled
    assert "SKIP LOCKED" in compiled
    assert str(tenant_id) in compiled


async def test_outbox_claim_recovers_expired_claim_with_skip_locked() -> None:
    tenant_id = uuid.uuid4()
    event = IngestionOutboxEvent(
        id=uuid.uuid4(),
        organization_id=tenant_id,
        observation_id=uuid.uuid4(),
        event_type="observation.accepted",
        event_key="event-key",
        status="claimed",
        available_at=datetime.now(UTC),
        lease_until=datetime.now(UTC) - timedelta(seconds=1),
        attempt_count=1,
    )
    session = _Session(event)
    repository = IngestionRepository(session, tenant_id)

    claimed = await repository.claim_outbox("worker-1")

    assert len(claimed) == 1
    assert claimed[0].status == "claimed"
    assert claimed[0].attempt_count == 2
    compiled = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in compiled
    assert "SKIP LOCKED" in compiled


def test_dispatcher_result_contains_only_ids() -> None:
    observation_id = uuid.uuid4()
    event_id = uuid.uuid4()
    lease_token = uuid.uuid4()
    result = _id_result(
        [
            SimpleNamespace(
                id=event_id,
                observation_id=observation_id,
                attempt_id=None,
                lease_token=lease_token,
            )
        ]
    )
    assert result == {
        "event_ids": [str(event_id)],
        "observation_ids": [str(observation_id)],
        "attempt_ids": [],
        "lease_tokens": [str(lease_token)],
    }

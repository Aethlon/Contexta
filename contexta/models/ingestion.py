from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from contexta.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(UTC)


class IngestionObservation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ingestion_observation"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="api")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_ingestion_observation_org_idempotency",
        ),
        Index("ix_ingestion_observation_org_id", "organization_id"),
        Index(
            "ix_ingestion_observation_dispatch",
            "organization_id",
            "status",
            "next_attempt_at",
            "created_at",
        ),
        Index(
            "ix_ingestion_observation_lease",
            "organization_id",
            "lease_until",
        ),
    )


class IngestionSourceTurn(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ingestion_source_turn"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_observation.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_turn_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "observation_id",
            "turn_index",
            name="uq_ingestion_source_turn_observation_index",
        ),
        Index("ix_ingestion_source_turn_org_id", "organization_id"),
        Index(
            "ix_ingestion_source_turn_observation",
            "organization_id",
            "observation_id",
            "turn_index",
        ),
        Index(
            "ix_ingestion_source_turn_source_id",
            "organization_id",
            "source_turn_id",
        ),
    )


class IngestionAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ingestion_attempt"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_observation.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing")
    worker_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "observation_id",
            "attempt_number",
            name="uq_ingestion_attempt_observation_number",
        ),
        Index("ix_ingestion_attempt_org_id", "organization_id"),
        Index(
            "ix_ingestion_attempt_observation",
            "organization_id",
            "observation_id",
            "attempt_number",
        ),
        Index(
            "ix_ingestion_attempt_status",
            "organization_id",
            "status",
            "started_at",
        ),
    )


class IngestionDeadLetter(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ingestion_dead_letter"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_observation.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_attempt.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "observation_id",
            name="uq_ingestion_dead_letter_observation",
        ),
        Index("ix_ingestion_dead_letter_org_id", "organization_id"),
        Index(
            "ix_ingestion_dead_letter_failed_at",
            "organization_id",
            "failed_at",
        ),
    )


class IngestionOutboxEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ingestion_outbox_event"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_observation.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_attempt.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="observation.accepted"
    )
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "event_key",
            name="uq_ingestion_outbox_event_org_key",
        ),
        Index("ix_ingestion_outbox_event_org_id", "organization_id"),
        Index(
            "ix_ingestion_outbox_event_dispatch",
            "organization_id",
            "status",
            "available_at",
            "lease_until",
            "created_at",
        ),
        Index(
            "ix_ingestion_outbox_event_observation",
            "organization_id",
            "observation_id",
        ),
    )


DurableObservation = IngestionObservation
SourceTurn = IngestionSourceTurn
AttemptRecord = IngestionAttempt
DeadLetterRecord = IngestionDeadLetter
OutboxEvent = IngestionOutboxEvent
ObservationRecord = IngestionObservation
IngestionOutbox = IngestionOutboxEvent

__all__ = [
    "AttemptRecord",
    "DeadLetterRecord",
    "DurableObservation",
    "IngestionAttempt",
    "IngestionDeadLetter",
    "IngestionObservation",
    "IngestionOutbox",
    "IngestionOutboxEvent",
    "IngestionSourceTurn",
    "ObservationRecord",
    "OutboxEvent",
    "SourceTurn",
]

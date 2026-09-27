from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, synonym, validates

from contexta.models.base import Base, UUIDPrimaryKeyMixin


class ImmutableRecordError(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _content_hash(content: str | None) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


class Episode(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "episode"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
    )
    memory_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memory_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("session.id", ondelete="SET NULL"),
        nullable=True,
    )
    episode_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_episode_id: Mapped[str | None] = synonym("external_id")
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    source_authority: Mapped[str] = mapped_column(
        String(100), nullable=False, default="unknown"
    )
    source_origin: Mapped[str] = mapped_column(String(255), nullable=False, default="unknown")
    model_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "episode_key",
            name="uq_episode_org_key",
        ),
        UniqueConstraint(
            "organization_id",
            "external_id",
            name="uq_episode_org_external_id",
        ),
        Index("ix_episode_org_session", "organization_id", "session_id"),
        Index(
            "ix_episode_org_user_occurred",
            "organization_id",
            "user_id",
            "occurred_at",
        ),
        Index("ix_episode_org_external", "organization_id", "external_id"),
        Index("ix_episode_org_key", "organization_id", "episode_key"),
        Index(
            "ix_episode_org_recorded",
            "organization_id",
            "recorded_at",
        ),
    )

    def __init__(self, **kwargs: Any) -> None:
        if "metadata" in kwargs and "metadata_" not in kwargs:
            kwargs["metadata_"] = kwargs.pop("metadata")
        if kwargs.get("content_hash") is None:
            kwargs["content_hash"] = _content_hash(kwargs.get("content"))
        super().__init__(**kwargs)

    @validates("content")
    def _set_content_hash(self, key: str, value: str | None) -> str | None:
        self.content_hash = _content_hash(value)
        return value


class SourceTurn(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "source_turn"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    episode_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("episode.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
    )
    memory_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memory_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("session.id", ondelete="SET NULL"),
        nullable=True,
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    source_turn_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_id: Mapped[str | None] = synonym("source_turn_id")
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_authority: Mapped[str] = mapped_column(
        String(100), nullable=False, default="unknown"
    )
    source_origin: Mapped[str] = mapped_column(String(255), nullable=False, default="unknown")
    model_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "episode_id",
            "turn_index",
            name="uq_source_turn_episode_index",
        ),
        UniqueConstraint(
            "organization_id",
            "source_turn_id",
            name="uq_source_turn_org_source_id",
        ),
        CheckConstraint("turn_index >= 0", name="turn_index_nonnegative"),
        Index("ix_source_turn_org_source_id", "organization_id", "source_turn_id"),
        Index(
            "ix_source_turn_org_episode",
            "organization_id",
            "episode_id",
            "turn_index",
        ),
    )

    def __init__(self, **kwargs: Any) -> None:
        if "metadata" in kwargs and "metadata_" not in kwargs:
            kwargs["metadata_"] = kwargs.pop("metadata")
        if kwargs.get("content_hash") is None:
            kwargs["content_hash"] = _content_hash(kwargs.get("content"))
        super().__init__(**kwargs)

    @validates("content")
    def _set_content_hash(self, key: str, value: str) -> str:
        self.content_hash = _content_hash(value)
        return value


class MemoryEvidence(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "memory_evidence"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
    )
    memory_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memory_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("session.id", ondelete="SET NULL"),
        nullable=True,
    )
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("episode.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_turn_id_record: Mapped[uuid.UUID | None] = mapped_column(
        "source_turn_id",
        UUID(as_uuid=True),
        ForeignKey("source_turn.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_turn_id: Mapped[uuid.UUID | None] = synonym("source_turn_id_record")
    observation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_observation.id", ondelete="SET NULL"),
        nullable=True,
    )
    fact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memory_fact.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    memory_fact_id: Mapped[uuid.UUID | None] = synonym("fact_id")
    evidence_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="source_turn"
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    locator: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_authority: Mapped[str] = mapped_column(
        String(100), nullable=False, default="unknown"
    )
    source_origin: Mapped[str] = mapped_column(String(255), nullable=False, default="unknown")
    model_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "evidence_key",
            name="uq_memory_evidence_org_key",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="confidence_range",
        ),
        Index("ix_memory_evidence_org_fact", "organization_id", "fact_id"),
        Index("ix_memory_evidence_org_episode", "organization_id", "episode_id"),
        Index(
            "ix_memory_evidence_org_turn",
            "organization_id",
            "source_turn_id",
        ),
        Index(
            "ix_memory_evidence_org_observation",
            "organization_id",
            "observation_id",
        ),
    )

    def __init__(self, **kwargs: Any) -> None:
        if "metadata" in kwargs and "metadata_" not in kwargs:
            kwargs["metadata_"] = kwargs.pop("metadata")
        super().__init__(**kwargs)


def _reject_immutable_mutation(mapper: Any, connection: Any, target: Any) -> None:
    raise ImmutableRecordError(f"{type(target).__name__} records are immutable")


for immutable_model in (Episode, SourceTurn, MemoryEvidence):
    event.listen(immutable_model, "before_update", _reject_immutable_mutation)
    event.listen(immutable_model, "before_delete", _reject_immutable_mutation)


EpisodeRecord = Episode
Turn = SourceTurn
Evidence = MemoryEvidence

__all__ = [
    "Episode",
    "EpisodeRecord",
    "Evidence",
    "ImmutableRecordError",
    "MemoryEvidence",
    "SourceTurn",
    "Turn",
]

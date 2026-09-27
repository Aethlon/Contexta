from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    event,
    inspect,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, synonym

from contexta.models.base import Base, UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MemoryFact(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "memory_fact"

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
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
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
    )
    subject: Mapped[str] = mapped_column(String(1000), nullable=False)
    predicate: Mapped[str] = mapped_column(String(255), nullable=False)
    object: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False, default="string")
    fact_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_at: Mapped[datetime] = synonym("valid_from")
    known_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    source_authority: Mapped[str] = mapped_column(
        String(100), nullable=False, default="unknown"
    )
    source_origin: Mapped[str] = mapped_column(String(255), nullable=False, default="unknown")
    model_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    authority: Mapped[str] = synonym("source_authority")
    origin: Mapped[str] = synonym("source_origin")
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lineage_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memory_fact.id", ondelete="SET NULL"),
        nullable=True,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="valid_range",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="confidence_range",
        ),
        CheckConstraint(
            "importance >= 0 AND importance <= 1",
            name="importance_range",
        ),
        Index("ix_memory_fact_org_fact_key", "organization_id", "fact_key"),
        Index(
            "ix_memory_fact_org_user_fact_key",
            "organization_id",
            "user_id",
            "fact_key",
        ),
        Index(
            "ix_memory_fact_org_subject_predicate",
            "organization_id",
            "subject",
            "predicate",
        ),
        Index(
            "ix_memory_fact_org_validity",
            "organization_id",
            "user_id",
            "valid_from",
            "valid_to",
        ),
        Index(
            "ix_memory_fact_org_source",
            "organization_id",
            "source_authority",
            "source_origin",
        ),
    )

    def __init__(self, **kwargs: Any) -> None:
        if "metadata" in kwargs and "metadata_" not in kwargs:
            kwargs["metadata_"] = kwargs.pop("metadata")
        super().__init__(**kwargs)


def _reject_fact_key_mutation(mapper: Any, connection: Any, target: MemoryFact) -> None:
    history = inspect(target).attrs.fact_key.history
    if history.has_changes():
        raise ValueError("MemoryFact.fact_key is immutable")


event.listen(MemoryFact, "before_update", _reject_fact_key_mutation)

Fact = MemoryFact

__all__ = ["Fact", "MemoryFact"]

"""SQLAlchemy models for the Dream Cycle Engine.

Includes DreamRecord (dream cycle execution logs) and
MissingMemoryCandidate (knowledge gaps identified during dreaming).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from contexta.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DreamRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Log entry for a dream cycle execution."""

    __tablename__ = "dream_record"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    cycle_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_count: Mapped[int] = mapped_column(nullable=False, default=0)
    insights_generated: Mapped[int] = mapped_column(nullable=False, default=0)
    cycles_completed: Mapped[int] = mapped_column(nullable=False, default=0)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class MissingMemoryCandidate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Knowledge gap identified by the Dream Cycle Engine."""

    __tablename__ = "missing_memory_candidate"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entity.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")

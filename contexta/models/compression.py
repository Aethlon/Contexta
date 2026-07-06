"""CompressedSummary SQLAlchemy model.

Compressed summaries generated from memory clusters for entities.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from contexta.models.base import Base, UUIDPrimaryKeyMixin


class CompressedSummary(Base, UUIDPrimaryKeyMixin):
    """Compressed summary generated from memory clusters for an entity."""

    __tablename__ = "compressed_summary"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entity.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    key_facts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_memory_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    generated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.utcnow()
    )

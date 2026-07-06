"""MemoryRecord SQLAlchemy model.

Represents a single unit of stored intelligence with metadata, content,
scores, embeddings, and lifecycle information.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Float, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from contexta.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MemoryRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Core memory storage table."""

    __tablename__ = "memory_record"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    utility_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    memory_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    valid_from: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.utcnow()
    )
    valid_to: Mapped[datetime | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536), nullable=True
    )

    # Full-text search vector (auto-maintained via trigger)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    __table_args__ = (
        # HNSW index for cosine similarity on embeddings
        Index(
            "ix_memory_record_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # B-tree composite indexes for tenant-scoped queries
        Index(
            "ix_memory_record_org_user_type",
            "organization_id",
            "user_id",
            "memory_type",
        ),
        Index(
            "ix_memory_record_org_user_state",
            "organization_id",
            "user_id",
            "memory_state",
        ),
        # Partial index for current truth queries (valid_to IS NULL)
        Index(
            "ix_memory_record_org_valid_to_partial",
            "organization_id",
            "valid_to",
            postgresql_where=text("valid_to IS NULL"),
        ),
        # GIN index for full-text search
        Index(
            "ix_memory_record_search_vector_gin",
            "search_vector",
            postgresql_using="gin",
        ),
    )

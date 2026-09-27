from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from contexta.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ArtifactRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "artifact"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    storage_etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_reference: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    extraction_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
        CheckConstraint(
            "char_length(content_hash) = 64", name="content_hash_length"
        ),
        UniqueConstraint(
            "organization_id",
            "storage_backend",
            "storage_key",
            name="uq_artifact_org_storage_object",
        ),
        Index("ix_artifact_org_created_at", "organization_id", "created_at"),
        Index(
            "ix_artifact_org_user_created_at",
            "organization_id",
            "user_id",
            "created_at",
        ),
        Index("ix_artifact_org_content_hash", "organization_id", "content_hash"),
    )

    @property
    def sha256(self) -> str:
        return self.content_hash


Artifact = ArtifactRecord

__all__ = ["Artifact", "ArtifactRecord"]

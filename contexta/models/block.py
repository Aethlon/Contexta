from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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
from contexta.models.evidence import ImmutableRecordError


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _content_hash(content: str | None, structured_data: Any) -> str:
    value = {"content": content, "structured_data": structured_data}
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class MemoryBlock(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "memory_block"

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
    block_key: Mapped[str] = mapped_column(String(255), nullable=False)
    block_type: Mapped[str] = mapped_column(String(50), nullable=False, default="memory")
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = synonym("name")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "memory_block_revision.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_memory_block_current_revision_id_memory_block_revision",
        ),
        nullable=True,
    )
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = synonym("current_version")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    model_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_authority: Mapped[str] = mapped_column(
        String(100), nullable=False, default="unknown"
    )
    source_origin: Mapped[str] = mapped_column(String(255), nullable=False, default="unknown")
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "block_key", name="uq_memory_block_org_key"),
        CheckConstraint("current_version >= 0", name="current_version_nonnegative"),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="valid_range",
        ),
        Index(
            "ix_memory_block_org_scope",
            "organization_id",
            "memory_user_id",
            "agent_id",
        ),
        Index("ix_memory_block_org_project", "organization_id", "project_id"),
        Index("ix_memory_block_org_current", "organization_id", "current_revision_id"),
        Index("ix_memory_block_org_type", "organization_id", "block_type", "status"),
    )

    def __init__(self, **kwargs: Any) -> None:
        if "metadata" in kwargs and "metadata_" not in kwargs:
            kwargs["metadata_"] = kwargs.pop("metadata")
        super().__init__(**kwargs)

    @validates("content", "structured_data")
    def _set_content_hash(self, key: str, value: Any) -> Any:
        content = value if key == "content" else self.content
        structured_data = value if key == "structured_data" else self.structured_data
        self.content_hash = _content_hash(content, structured_data)
        return value


class MemoryBlockRevision(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "memory_block_revision"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memory_block.id", ondelete="CASCADE"),
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
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version: Mapped[int] = synonym("revision_number")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    model_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_authority: Mapped[str] = mapped_column(
        String(100), nullable=False, default="unknown"
    )
    source_origin: Mapped[str] = mapped_column(String(255), nullable=False, default="unknown")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="SET NULL"),
        nullable=True,
    )
    supersedes_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memory_block_revision.id", ondelete="SET NULL"),
        nullable=True,
    )
    parent_revision_id: Mapped[uuid.UUID | None] = synonym("supersedes_revision_id")
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "block_id",
            "revision_number",
            name="uq_memory_block_revision_number",
        ),
        CheckConstraint("revision_number > 0", name="revision_number_positive"),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="valid_range",
        ),
        Index(
            "ix_memory_block_revision_org_block",
            "organization_id",
            "block_id",
            "revision_number",
        ),
        Index(
            "ix_memory_block_revision_org_hash",
            "organization_id",
            "content_hash",
        ),
        Index(
            "ix_memory_block_revision_org_created",
            "organization_id",
            "created_at",
        ),
    )

    def __init__(self, **kwargs: Any) -> None:
        if "metadata" in kwargs and "metadata_" not in kwargs:
            kwargs["metadata_"] = kwargs.pop("metadata")
        super().__init__(**kwargs)

    @validates("content", "structured_data")
    def _set_content_hash(self, key: str, value: Any) -> Any:
        content = value if key == "content" else self.content
        structured_data = value if key == "structured_data" else self.structured_data
        self.content_hash = _content_hash(content, structured_data)
        return value


def _reject_immutable_mutation(mapper: Any, connection: Any, target: Any) -> None:
    raise ImmutableRecordError(f"{type(target).__name__} records are immutable")


event.listen(MemoryBlockRevision, "before_update", _reject_immutable_mutation)
event.listen(MemoryBlockRevision, "before_delete", _reject_immutable_mutation)

MemoryBlockVersion = MemoryBlockRevision
Block = MemoryBlock

__all__ = [
    "Block",
    "MemoryBlock",
    "MemoryBlockRevision",
    "MemoryBlockVersion",
]

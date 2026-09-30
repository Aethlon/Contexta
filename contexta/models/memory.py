"""MemoryRecord SQLAlchemy model.

Represents a single unit of stored intelligence with metadata, content,
scores, embeddings, and lifecycle information.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    desc,
    event,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, synonym, validates

from contexta.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Envelope prefix written by `contexta.core.crypto.vault.encrypt_content`.
# `encrypt_content` itself does not check it -- only `decrypt_content` does --
# so handing it an already-sealed value nests one envelope inside the second and
# decrypts to the inner token rather than to the sentence. Every seal path in
# this module therefore checks the prefix first.
ENCRYPTED_CONTENT_PREFIX = "enc:v1:"


def _coerce_scope_uuid(value: object, field_name: str) -> uuid.UUID | None:
    if value is None:
        if field_name in {"user_id", "organization_id"}:
            raise ValueError(f"{field_name} cannot be null.")
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a UUID.") from exc


class MemoryContentDecryptionError(RuntimeError):
    pass


def seal_content_for_storage(record: MemoryRecord) -> None:
    """Encrypt ``record.content`` in place, once, keyed by its own organization.

    Called from the mapper-level flush hooks at the bottom of this module so that
    *every* ORM write path seals its content: the ingestion orchestrator's
    ``session.add_all``, ``MemoryRepository.create``, a later in-session content
    change, and any writer added after this fix. The guarantee belongs to the
    model rather than to a call site, because a call-site guarantee is exactly
    what let the orchestrator persist cleartext for 89% of stored memories while
    the code and the docs advertised authenticated at-rest encryption.

    Idempotent, and a no-op for ``None`` and for non-text values. The prefix
    check is what keeps a caller that already sealed its own value --
    ``MemoryRepository.create`` and ``update_by_id`` both do -- from nesting a
    second envelope inside the first.
    """
    content = record.content
    if content is None or not isinstance(content, str):
        return
    if content.startswith(ENCRYPTED_CONTENT_PREFIX):
        return

    from contexta.core.crypto.vault import encrypt_content

    organization_id = record.organization_id
    record.content = encrypt_content(
        content,
        str(organization_id) if organization_id is not None else None,
    )


def _seal_content_before_insert(mapper: Any, connection: Any, target: MemoryRecord) -> None:
    seal_content_for_storage(target)


def _seal_content_before_update(mapper: Any, connection: Any, target: MemoryRecord) -> None:
    # Only a content value this flush is actually writing needs sealing. Without
    # the history check every update to any column would re-seal an untouched
    # content column with a fresh nonce, rewriting bytes nobody changed.
    if inspect(target).attrs.content.history.has_changes():
        seal_content_for_storage(target)


class MemoryRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Core memory storage table."""

    __tablename__ = "memory_record"

    @validates(
        "user_id",
        "memory_user_id",
        "agent_id",
        "project_id",
        "organization_id",
        "session_id",
    )
    def _validate_scope_uuid(self, key: str, value: object) -> uuid.UUID | None:
        return _coerce_scope_uuid(value, key)

    @property
    def plaintext_content(self) -> str:
        from contexta.core.crypto.vault import decrypt_content

        raw_content = self.content
        if raw_content is None:
            return ""
        if not isinstance(raw_content, str):
            raise MemoryContentDecryptionError(
                f"Memory {self.id} has non-text content; verify CONTEXTA_SECRET_KEY and the tenant key."
            )
        if not raw_content.startswith(ENCRYPTED_CONTENT_PREFIX):
            return raw_content
        try:
            value = decrypt_content(raw_content, str(self.organization_id))
        except Exception as exc:
            raise MemoryContentDecryptionError(
                f"Memory {self.id} could not be decrypted; verify CONTEXTA_SECRET_KEY and the tenant key "
                "before embedding or deduplication."
            ) from exc
        if value is None or value == raw_content or value == "[Encrypted - Decryption Key Mismatch]":
            raise MemoryContentDecryptionError(
                f"Memory {self.id} cannot be decrypted with its organization key; "
                "verify CONTEXTA_SECRET_KEY and the tenant key before embedding or deduplication."
            )
        return value

    def get_plaintext_content(self) -> str:
        return self.plaintext_content

    @property
    def active_embedding(self) -> list[float] | None:
        if self.embedding_1024 is not None:
            return self.embedding_1024
        return self.embedding

    @property
    def embedding_metadata(self) -> dict[str, str | int | None]:
        return {
            "embedding_profile": self.embedding_profile,
            "embedding_model": self.embedding_model,
            "embedding_version": self.embedding_version,
            "embedding_dimensions": self.embedding_dimensions,
        }

    embedding_model_version = synonym("embedding_version")

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    memory_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
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
    event_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    temporal_precision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temporal_basis: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fact_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lineage_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536), nullable=True
    )
    embedding_1024: Mapped[list[float] | None] = mapped_column(
        Vector(1024), nullable=True
    )
    embedding_profile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    search_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "embedding_dimensions IS NULL OR embedding_dimensions IN (1024, 1536)",
            name="embedding_dimensions",
        ),
        # HNSW index for cosine similarity on embeddings
        Index(
            "ix_memory_record_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_memory_record_embedding_1024_hnsw",
            "embedding_1024",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding_1024": "vector_cosine_ops"},
        ),
        Index(
            "ix_memory_record_org_embedding_profile",
            "organization_id",
            "embedding_profile",
            "embedding_dimensions",
        ),
        # B-tree composite indexes for tenant-scoped queries
        Index(
            "ix_memory_record_org_user_type",
            "organization_id",
            "user_id",
            "memory_type",
        ),
        Index(
            "ix_memory_record_org_scope",
            "organization_id",
            "user_id",
            "memory_user_id",
            "agent_id",
            "project_id",
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
            "user_id",
            postgresql_where=text("valid_to IS NULL"),
        ),
        # Current-truth partial indexes: every hot read is
        # `WHERE valid_to IS NULL`, so the predicate keeps the superseded
        # rows out of the index and keeps the ordering column usable.
        Index(
            "ix_memory_record_event_current",
            "organization_id",
            "user_id",
            desc("event_at"),
            postgresql_where=text("valid_to IS NULL"),
        ),
        Index(
            "ix_memory_record_created_current",
            "organization_id",
            "user_id",
            desc("created_at"),
            postgresql_where=text("valid_to IS NULL"),
        ),
        Index(
            "ix_memory_record_fact_key_current",
            "organization_id",
            "user_id",
            "fact_key",
            postgresql_where=text("valid_to IS NULL"),
        ),
        # GIN index for full-text search
        Index(
            "ix_memory_record_search_vector_gin",
            "search_vector",
            postgresql_using="gin",
        ),
        # GIN index for tag containment filters
        Index(
            "ix_memory_record_tags_gin",
            "tags",
            postgresql_using="gin",
        ),
        # Read-age decay sweeps only touch unpinned, live rows
        Index(
            "ix_memory_record_last_accessed",
            "organization_id",
            "last_accessed_at",
            postgresql_where=text("is_pinned = false AND valid_to IS NULL"),
        ),
        Index(
            "ix_memory_record_org_user_event",
            "organization_id",
            "user_id",
            "event_at",
        ),
        Index(
            "ix_memory_record_org_fact_key",
            "organization_id",
            "user_id",
            "fact_key",
        ),
        # Bitemporal range support: mirrors ix_memory_fact_org_validity so an
        # "as of T" lookup is answered by the index rather than a scan.
        Index(
            "ix_memory_record_org_validity",
            "organization_id",
            "user_id",
            "valid_from",
            "valid_to",
        ),
    )


# Sealing content is a property of the column, not of any writer. Registered at
# the mapper rather than on a session's `before_flush` for two reasons:
#
# 1. A `before_flush` listener attached to `contexta.db.AsyncSessionFactory`
#    only sees sessions that factory built. `contexta/mcp/service.py`, the
#    LoCoMo and LongMemEval harnesses, and the CHIMERA runner each construct
#    their own sessionmaker, and a factory-scoped hook would let every one of
#    them write cleartext without complaint.
# 2. Mapper hooks fire per row at the moment the INSERT/UPDATE parameters are
#    collected, so the sealed value is the value that reaches the wire, and
#    mutating the attribute there is a documented, supported operation. A
#    `before_flush` listener mutates objects the unit of work has already
#    planned, and would need a second `flush()` to be sure of the result.
#
# Neither can see Core DML -- `session.execute(insert(MemoryRecord), ...)` or
# `update(MemoryRecord).values(content=...)` -- which bypasses the ORM
# entirely. The single content-writing Core statement in the tree is
# `TenantScopedRepository.update_by_id`, and `MemoryRepository` seals the value
# before handing it over, so that path is covered by construction rather than
# by an event.
event.listen(MemoryRecord, "before_insert", _seal_content_before_insert)
event.listen(MemoryRecord, "before_update", _seal_content_before_update)

__all__ = [
    "ENCRYPTED_CONTENT_PREFIX",
    "MemoryContentDecryptionError",
    "MemoryRecord",
    "seal_content_for_storage",
]

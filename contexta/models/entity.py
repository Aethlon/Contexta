"""SQLAlchemy models for Entity, EntityEdge, and MemoryEntityLink.

Represents the knowledge graph: entities (nodes), edges (relationships),
and links between memories and entities.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from contexta.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Every `relationship_type` the system is allowed to persist.
#
# This is the union of two producers, and it is deliberately a superset of
# both:
#   * `core.entities.relation_extractor.RELATION_PATTERNS` plus its
#     `related_to` backfill -- 24 literals, derived in that module.
#   * `core.types.RelationType` -- 7 members, 3 of which the extractor never
#     emits (`likes`, `owns`, `superseded_by`) but
#     `core.entities.resolver.Resolver.create_edge` writes verbatim.
#
# A CHECK constraint on the narrower of the two sets would turn
# `create_edge(relationship_type=RelationType.LIKES)` into a CheckViolation, so
# both sets are admitted here. `RelationType` is the set that should shrink;
# until it is reconciled with the extractor, this frozenset is the source of
# truth for the column.
ALLOWED_RELATIONSHIP_TYPES: frozenset[str] = frozenset({
    # relation_extractor RELATION_PATTERNS, forward and backward literals.
    "integrates_with", "integrated_by",
    "used_by", "uses",
    "depends_on", "dependency_of",
    "works_on", "worked_on_by",
    "works_at", "employs",
    "created_by", "created",
    "part_of", "has_component",
    "prefers", "preferred_by",
    "avoids", "avoided_by",
    "collaborates_with",
    "located_in", "location_of",
    "is_a", "has_instance",
    # relation_extractor's bounded co-occurrence backfill.
    "related_to",
    # RelationType members the extractor has no pattern for.
    "likes", "owns", "superseded_by",
})

# Sorted so the rendered constraint text is stable across processes; the order
# the literals are written in has no meaning to the database.
_RELATIONSHIP_TYPE_CHECK = "relationship_type IN ({})".format(
    ", ".join(f"'{value}'" for value in sorted(ALLOWED_RELATIONSHIP_TYPES))
)


class Entity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A node in the knowledge graph (person, project, technology, etc.)."""

    __tablename__ = "entity"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    aggregated_attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.utcnow()
    )

    __table_args__ = (
        Index(
            "ix_entity_org_user_type",
            "organization_id",
            "user_id",
            "entity_type",
        ),
        # Trigram index for fuzzy entity-name recall during resolution.
        Index(
            "ix_entity_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        # Case-insensitive entity identity, enforced by the database rather
        # than by a read-then-write check, so two concurrent ingestions of
        # "Kubernetes" / "kubernetes" collapse onto one row instead of racing
        # to insert two. Revision 018 merged the duplicates this could not
        # previously tolerate.
        #
        # Declared as a unique Index rather than a UniqueConstraint because
        # PostgreSQL allows an expression in a unique index and not in a table
        # constraint, and SQLAlchemy mirrors that: a UniqueConstraint cannot
        # hold `func.lower(name)` at all. It is the same object the database
        # would build for `UNIQUE (organization_id, user_id, lower(name))` and
        # `ON CONFLICT` on that column list resolves to it, so
        # `EntityRepository.upsert_by_name` and this declaration must stay in
        # step.
        #
        # This index replaces the non-unique `ix_entity_identity` from revision
        # 015 rather than sitting beside it: the two would have had identical
        # column lists, so keeping both would double every write to this table
        # for no lookup benefit. It is named `uq_` to signal that it is
        # load-bearing for `ON CONFLICT`, not because of the `ix` convention --
        # an explicitly named Index keeps its name.
        Index(
            "uq_entity_identity",
            "organization_id",
            "user_id",
            # `text("name")`, not `column("name")`: an index expression must be a
            # SQL fragment. Passing a bare Column() adds an unnamed column to the
            # table's column collection, which SQLAlchemy rejects at import time
            # with "Can't add unnamed column to column collection".
            func.lower(text("name")),
            unique=True,
        ),
    )


class EntityEdge(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A typed relationship edge between two entities."""

    __tablename__ = "entity_edge"

    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entity.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entity.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )

    __table_args__ = (
        Index("ix_entity_edge_source", "source_entity_id"),
        Index("ix_entity_edge_target", "target_entity_id"),

        # Both traversal directions of a scoped multi-hop walk, so a hop can
        # stay inside the tenant without a second index scan.
        Index(
            "ix_entity_edge_scoped",
            "organization_id",
            "source_entity_id",
            "target_entity_id",
        ),
        Index(
            "ix_entity_edge_scoped_rev",
            "organization_id",
            "target_entity_id",
            "source_entity_id",
        ),
        UniqueConstraint(
            "organization_id",
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            name="uq_entity_edge_identity",
        ),
        CheckConstraint("source_entity_id <> target_entity_id", name="no_self_loop"),
        # relationship_type was free-text String(50), so a typo or a
        # half-finished extractor silently became a new edge type that no
        # reader knows how to weight. ALLOWED_RELATIONSHIP_TYPES pins it.
        CheckConstraint(_RELATIONSHIP_TYPE_CHECK, name="relationship_type_known"),
    )


class MemoryEntityLink(Base, TimestampMixin):
    """Junction table linking memories to entities."""

    __tablename__ = "memory_entity_link"

    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memory_record.id", ondelete="CASCADE"),
        primary_key=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entity.id", ondelete="CASCADE"),
        primary_key=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )

    __table_args__ = (
        # The primary key is (memory_id, entity_id), so `WHERE entity_id = ?`
        # cannot use it: entity_id is the second key column. Graph expansion
        # filters on entity_id first, hence the reversed order here.
        Index("ix_mem_entity_link_entity", "entity_id", "memory_id"),
    )

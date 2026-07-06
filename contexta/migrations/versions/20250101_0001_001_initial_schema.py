"""Initial schema with all tables and indexes.

Revision ID: 001
Revises: None
Create Date: 2025-01-01 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable required extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- session ---
    op.create_table(
        "session",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
    )

    # --- memory_record ---
    op.create_table(
        "memory_record",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("memory_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_data", JSONB, nullable=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("utility_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("tags", ARRAY(sa.String()), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column(
            "memory_state", sa.String(20), nullable=False, server_default="active"
        ),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("valid_from", sa.DateTime(), nullable=False),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("search_vector", TSVECTOR, nullable=True),
    )

    # memory_record indexes
    op.create_index(
        "ix_memory_record_embedding_hnsw",
        "memory_record",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_memory_record_org_user_type",
        "memory_record",
        ["organization_id", "user_id", "memory_type"],
    )
    op.create_index(
        "ix_memory_record_org_user_state",
        "memory_record",
        ["organization_id", "user_id", "memory_state"],
    )
    op.create_index(
        "ix_memory_record_org_valid_to_partial",
        "memory_record",
        ["organization_id", "valid_to"],
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "ix_memory_record_search_vector_gin",
        "memory_record",
        ["search_vector"],
        postgresql_using="gin",
    )

    # --- entity ---
    op.create_table(
        "entity",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("aggregated_attributes", JSONB, nullable=True),
        sa.Column("last_updated", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_entity_org_user_type",
        "entity",
        ["organization_id", "user_id", "entity_type"],
    )

    # --- entity_edge ---
    op.create_table(
        "entity_edge",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_entity_id",
            sa.Uuid(),
            sa.ForeignKey("entity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_entity_id",
            sa.Uuid(),
            sa.ForeignKey("entity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(50), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_entity_edge_source", "entity_edge", ["source_entity_id"])
    op.create_index("ix_entity_edge_target", "entity_edge", ["target_entity_id"])

    # --- memory_entity_link ---
    op.create_table(
        "memory_entity_link",
        sa.Column(
            "memory_id",
            sa.Uuid(),
            sa.ForeignKey("memory_record.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "entity_id",
            sa.Uuid(),
            sa.ForeignKey("entity.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # --- memory_version ---
    op.create_table(
        "memory_version",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "memory_id",
            sa.Uuid(),
            sa.ForeignKey("memory_record.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "superseded_by_id",
            sa.Uuid(),
            sa.ForeignKey("memory_record.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_data", JSONB, nullable=True),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("valid_from", sa.DateTime(), nullable=False),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # --- audit_log ---
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("operation_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_audit_log_org_created_at",
        "audit_log",
        ["organization_id", "created_at"],
    )

    # --- retrieval_feedback ---
    op.create_table(
        "retrieval_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "memory_id",
            sa.Uuid(),
            sa.ForeignKey("memory_record.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("context_request_id", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("signal", sa.String(20), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_retrieval_feedback_memory_signal",
        "retrieval_feedback",
        ["memory_id", "signal"],
    )

    # --- memory_policy ---
    op.create_table(
        "memory_policy",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("store_rules", JSONB, nullable=True),
        sa.Column("ignore_rules", JSONB, nullable=True),
        sa.Column("priority_weights", JSONB, nullable=True),
        sa.Column(
            "is_builtin", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # --- custom_schema ---
    op.create_table(
        "custom_schema",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("field_definitions", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # --- semantic_cluster ---
    op.create_table(
        "semantic_cluster",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # --- cluster_membership ---
    op.create_table(
        "cluster_membership",
        sa.Column(
            "cluster_id",
            sa.Uuid(),
            sa.ForeignKey("semantic_cluster.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "memory_id",
            sa.Uuid(),
            sa.ForeignKey("memory_record.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("added_at", sa.DateTime(), nullable=False),
    )

    # --- compressed_summary ---
    op.create_table(
        "compressed_summary",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "entity_id",
            sa.Uuid(),
            sa.ForeignKey("entity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("key_facts", JSONB, nullable=True),
        sa.Column(
            "confidence", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column(
            "source_memory_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "is_stale", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
    )

    # --- missing_memory_candidate ---
    op.create_table(
        "missing_memory_candidate",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column(
            "related_entity_id",
            sa.Uuid(),
            sa.ForeignKey("entity.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status", sa.String(30), nullable=False, server_default="open"
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # Create tsvector trigger for memory_record full-text search
    op.execute("""
        CREATE OR REPLACE FUNCTION memory_record_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.content, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(array_to_string(NEW.tags, ' '), '')), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER memory_record_search_vector_trigger
        BEFORE INSERT OR UPDATE OF title, content, tags
        ON memory_record
        FOR EACH ROW
        EXECUTE FUNCTION memory_record_search_vector_update();
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS memory_record_search_vector_trigger ON memory_record"
    )
    op.execute("DROP FUNCTION IF EXISTS memory_record_search_vector_update()")

    op.drop_table("missing_memory_candidate")
    op.drop_table("compressed_summary")
    op.drop_table("cluster_membership")
    op.drop_table("semantic_cluster")
    op.drop_table("custom_schema")
    op.drop_table("memory_policy")
    op.drop_table("retrieval_feedback")
    op.drop_table("audit_log")
    op.drop_table("memory_version")
    op.drop_table("memory_entity_link")
    op.drop_table("entity_edge")
    op.drop_table("entity")
    op.drop_table("memory_record")
    op.drop_table("session")

    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS vector")

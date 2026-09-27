from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memory_record",
        sa.Column("embedding_1024", Vector(1024), nullable=True),
    )
    op.add_column(
        "memory_record",
        sa.Column("embedding_profile", sa.String(64), nullable=True),
    )
    op.add_column(
        "memory_record",
        sa.Column("embedding_model", sa.String(255), nullable=True),
    )
    op.add_column(
        "memory_record",
        sa.Column("embedding_version", sa.String(128), nullable=True),
    )
    op.add_column(
        "memory_record",
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_memory_record_embedding_dimensions",
        "memory_record",
        "embedding_dimensions IS NULL OR embedding_dimensions IN (1024, 1536)",
    )
    op.create_index(
        "ix_memory_record_embedding_1024_hnsw",
        "memory_record",
        ["embedding_1024"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding_1024": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_memory_record_org_embedding_profile",
        "memory_record",
        ["organization_id", "embedding_profile", "embedding_dimensions"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_memory_record_org_embedding_profile",
        table_name="memory_record",
    )
    op.drop_index(
        "ix_memory_record_embedding_1024_hnsw",
        table_name="memory_record",
    )
    op.drop_constraint(
        "ck_memory_record_embedding_dimensions",
        "memory_record",
        type_="check",
    )
    op.drop_column("memory_record", "embedding_dimensions")
    op.drop_column("memory_record", "embedding_version")
    op.drop_column("memory_record", "embedding_model")
    op.drop_column("memory_record", "embedding_profile")
    op.drop_column("memory_record", "embedding_1024")

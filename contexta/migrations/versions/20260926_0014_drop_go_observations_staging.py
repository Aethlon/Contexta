"""Drop the retired Go data-plane `observations` staging table.

The Go data-plane is deleted. The gateway is now a stateless TLS edge
(API-key verification + rate limiting + reverse proxy) and the Python API
is the sole data path. The `observations` staging table was only ever
written by the Go service, and the `drain_go_staging` Celery task that
read it has been removed. The table had no HNSW or GIN index and was
never a retrieval target; `memory_record` is.

Revision ID: 014
Revises: 013
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("observations")


def downgrade() -> None:
    # Mirrors the table created by revision 005 so the downgrade is faithful.
    op.create_table(
        "observations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(100), nullable=False, server_default="sdk"),
        sa.Column("type", sa.String(50), nullable=False, server_default="episodic"),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("tags", JSONB, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("redacted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_observations_tenant_status",
        "observations",
        ["tenant_id", "status"],
    )

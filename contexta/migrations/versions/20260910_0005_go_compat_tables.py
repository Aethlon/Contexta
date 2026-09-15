"""Go data-plane compat tables (observations/sessions).

Revision ID: 005
Revises: 004
Create Date: 2026-09-10

Go data-plane expects `observations` and `sessions` (plural) tables,
while Python core uses `memory_record` / `session` (singular).
This migration creates the Go tables so the data-plane no longer crashes
with UndefinedTable. Long-term: Go should read memory_record directly;
these tables are the fast ingest buffer (see docs/OSS_CORE_PLAN.md).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

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

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("provider", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("observations")

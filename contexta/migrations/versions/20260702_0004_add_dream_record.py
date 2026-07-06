"""Create dream_record table.

Revision ID: 004
Revises: 003
Create Date: 2026-07-02 13:30:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create dream_record table."""
    op.create_table(
        "dream_record",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("cycle_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("memory_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("insights_generated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cycles_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extra_data", JSONB(), nullable=True, server_default="{}"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_dream_record_user_id", "dream_record", ["user_id"])
    op.create_index("ix_dream_record_org_id", "dream_record", ["organization_id"])


def downgrade() -> None:
    """Drop dream_record table."""
    op.drop_index("ix_dream_record_org_id", table_name="dream_record")
    op.drop_index("ix_dream_record_user_id", table_name="dream_record")
    op.drop_table("dream_record")

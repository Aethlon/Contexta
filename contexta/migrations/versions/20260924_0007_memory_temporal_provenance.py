from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memory_record",
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "memory_record",
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "memory_record",
        sa.Column("temporal_precision", sa.String(32), nullable=True),
    )
    op.add_column(
        "memory_record",
        sa.Column("temporal_basis", sa.String(64), nullable=True),
    )
    op.add_column(
        "memory_record",
        sa.Column("fact_key", sa.String(128), nullable=True),
    )
    op.add_column(
        "memory_record",
        sa.Column("lineage_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "memory_record",
        sa.Column("source_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "memory_record",
        sa.Column("source_message_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_memory_record_org_user_event",
        "memory_record",
        ["organization_id", "user_id", "event_at"],
    )
    op.create_index(
        "ix_memory_record_org_fact_key",
        "memory_record",
        ["organization_id", "user_id", "fact_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_record_org_fact_key", table_name="memory_record")
    op.drop_index("ix_memory_record_org_user_event", table_name="memory_record")
    op.drop_column("memory_record", "source_message_id")
    op.drop_column("memory_record", "source_id")
    op.drop_column("memory_record", "lineage_id")
    op.drop_column("memory_record", "fact_key")
    op.drop_column("memory_record", "temporal_basis")
    op.drop_column("memory_record", "temporal_precision")
    op.drop_column("memory_record", "observed_at")
    op.drop_column("memory_record", "event_at")

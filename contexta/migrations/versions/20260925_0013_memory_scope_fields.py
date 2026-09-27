from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("memory_record", sa.Column("memory_user_id", sa.Uuid(), nullable=True))
    op.add_column("memory_record", sa.Column("agent_id", sa.Uuid(), nullable=True))
    op.add_column("memory_record", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_memory_record_org_scope",
        "memory_record",
        ["organization_id", "user_id", "memory_user_id", "agent_id", "project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_record_org_scope", table_name="memory_record")
    op.drop_column("memory_record", "project_id")
    op.drop_column("memory_record", "agent_id")
    op.drop_column("memory_record", "memory_user_id")

"""Create api_key table.

Revision ID: 002
Revises: 001
Create Date: 2026-06-13 12:00:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create api_key table and associated indexes."""
    op.create_table(
        "api_key",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("scopes", ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_api_key_token_hash", "api_key", ["token_hash"], unique=True)
    op.create_index("ix_api_key_organization_id", "api_key", ["organization_id"])


def downgrade() -> None:
    """Drop api_key table and associated indexes."""
    op.drop_index("ix_api_key_organization_id", table_name="api_key")
    op.drop_index("ix_api_key_token_hash", table_name="api_key")
    op.drop_table("api_key")

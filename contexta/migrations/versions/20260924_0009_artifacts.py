from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artifact",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_backend", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("storage_etag", sa.String(length=255), nullable=True),
        sa.Column("original_reference", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("extraction_method", sa.String(length=32), nullable=True),
        sa.Column(
            "extraction_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_artifact_size_nonnegative"),
        sa.CheckConstraint(
            "char_length(content_hash) = 64", name="ck_artifact_content_hash_length"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "storage_backend",
            "storage_key",
            name="uq_artifact_org_storage_object",
        ),
    )
    op.create_index(
        "ix_artifact_org_created_at",
        "artifact",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_artifact_org_user_created_at",
        "artifact",
        ["organization_id", "user_id", "created_at"],
    )
    op.create_index(
        "ix_artifact_org_content_hash",
        "artifact",
        ["organization_id", "content_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_artifact_org_content_hash", table_name="artifact")
    op.drop_index("ix_artifact_org_user_created_at", table_name="artifact")
    op.drop_index("ix_artifact_org_created_at", table_name="artifact")
    op.drop_table("artifact")

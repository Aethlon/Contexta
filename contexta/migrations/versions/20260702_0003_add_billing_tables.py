"""Create account, organization, project, and billing/usage tables.

Revision ID: 003
Revises: 002
Create Date: 2026-07-02 00:00:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, CITEXT, BIGINT

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    # --- account ---
    op.create_table(
        "account",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", CITEXT(), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("oauth_provider", sa.String(50), nullable=True),
        sa.Column("oauth_subject", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("totp_secret", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_account_email", "account", ["email"], unique=True)

    # --- organization ---
    op.create_table(
        "organization",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("plan_code", sa.String(50), nullable=False, server_default="free"),
        sa.Column("dodo_customer_id", sa.String(100), nullable=True),
        sa.Column("dodo_subscription_id", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_organization_slug", "organization", ["slug"], unique=True)

    # --- organization_member ---
    op.create_table(
        "organization_member",
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "account_id", name="pk_organization_member"),
    )

    # --- project ---
    op.create_table(
        "project",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("region", sa.String(50), nullable=False, server_default="us-east-1"),
        sa.Column("hard_cap", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_organization_id", "project", ["organization_id"])
    op.create_unique_constraint("uq_project_org_slug", "project", ["organization_id", "slug"])

    # --- usage_event (partitioned) ---
    op.execute("""
        CREATE TABLE usage_event (
            id UUID NOT NULL,
            organization_id UUID NOT NULL,
            project_id UUID NOT NULL,
            api_key_id UUID NOT NULL,
            user_id UUID,
            endpoint VARCHAR(500) NOT NULL,
            method VARCHAR(10) NOT NULL,
            classification VARCHAR(50) NOT NULL,
            units INTEGER NOT NULL DEFAULT 0,
            bytes_in INTEGER NOT NULL DEFAULT 0,
            bytes_out INTEGER NOT NULL DEFAULT 0,
            llm_tokens_in INTEGER NOT NULL DEFAULT 0,
            llm_tokens_out INTEGER NOT NULL DEFAULT 0,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            status_code SMALLINT NOT NULL,
            request_id VARCHAR(100) NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL,
            region VARCHAR(50) NOT NULL
        ) PARTITION BY RANGE (occurred_at)
    """)

    # Create initial monthly partitions
    for year, month in [(2026, 1), (2026, 2), (2026, 3), (2026, 4), (2026, 5), (2026, 6),
                         (2026, 7), (2026, 8), (2026, 9), (2026, 10), (2026, 11), (2026, 12),
                         (2027, 1), (2027, 2), (2027, 3)]:
        start = f"{year}-{month:02d}-01"
        end_year = year + (month // 12)
        end_month = (month % 12) + 1
        end = f"{end_year}-{end_month:02d}-01"
        partition_name = f"usage_event_{year}_{month:02d}"
        op.execute(f"""
            CREATE TABLE {partition_name} PARTITION OF usage_event
            FOR VALUES FROM ('{start}') TO ('{end}')
        """)

    op.create_index("ix_usage_event_org_occurred", "usage_event", ["organization_id", "occurred_at"])
    op.create_index("ix_usage_event_org_classification", "usage_event", ["organization_id", "classification"])

    # --- usage_daily ---
    op.create_table(
        "usage_daily",
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("classification", sa.String(50), nullable=False),
        sa.Column("units", BIGINT(), nullable=False, server_default="0"),
        sa.Column("llm_tokens_in", BIGINT(), nullable=False, server_default="0"),
        sa.Column("llm_tokens_out", BIGINT(), nullable=False, server_default="0"),
        sa.Column("bytes_in", BIGINT(), nullable=False, server_default="0"),
        sa.Column("bytes_out", BIGINT(), nullable=False, server_default="0"),
        sa.Column("request_count", BIGINT(), nullable=False, server_default="0"),
        sa.Column("cost_micros", BIGINT(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("organization_id", "project_id", "day", "classification", name="pk_usage_daily"),
    )

    # --- usage_period ---
    op.create_table(
        "usage_period",
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("plan_code", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("observations", BIGINT(), nullable=False, server_default="0"),
        sa.Column("retrievals", BIGINT(), nullable=False, server_default="0"),
        sa.Column("reranks", BIGINT(), nullable=False, server_default="0"),
        sa.Column("memory_writes", BIGINT(), nullable=False, server_default="0"),
        sa.Column("active_memories", BIGINT(), nullable=False, server_default="0"),
        sa.Column("overage_cents", BIGINT(), nullable=False, server_default="0"),
        sa.Column("invoice_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("organization_id", "period_start", name="pk_usage_period"),
    )


def downgrade() -> None:
    op.drop_table("usage_period")
    op.drop_table("usage_daily")
    for year, month in [(2026, 1), (2026, 2), (2026, 3), (2026, 4), (2026, 5), (2026, 6),
                         (2026, 7), (2026, 8), (2026, 9), (2026, 10), (2026, 11), (2026, 12),
                         (2027, 1), (2027, 2), (2027, 3)]:
        op.drop_table(f"usage_event_{year}_{month:02d}")
    op.drop_table("usage_event")
    op.drop_table("project")
    op.drop_table("organization_member")
    op.drop_table("organization")
    op.drop_table("account")

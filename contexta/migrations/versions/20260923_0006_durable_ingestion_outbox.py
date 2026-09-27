from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_observation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("source", sa.String(100), nullable=False, server_default="api"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(255), nullable=True),
        sa.Column("lease_token", UUID(as_uuid=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_ingestion_observation_org_idempotency",
        ),
    )
    op.create_index(
        "ix_ingestion_observation_org_id",
        "ingestion_observation",
        ["organization_id"],
    )
    op.create_index(
        "ix_ingestion_observation_dispatch",
        "ingestion_observation",
        ["organization_id", "status", "next_attempt_at", "created_at"],
    )
    op.create_index(
        "ix_ingestion_observation_lease",
        "ingestion_observation",
        ["organization_id", "lease_until"],
    )

    op.create_table(
        "ingestion_source_turn",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "observation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ingestion_observation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_turn_id", sa.String(255), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "observation_id",
            "turn_index",
            name="uq_ingestion_source_turn_observation_index",
        ),
    )
    op.create_index(
        "ix_ingestion_source_turn_org_id",
        "ingestion_source_turn",
        ["organization_id"],
    )
    op.create_index(
        "ix_ingestion_source_turn_observation",
        "ingestion_source_turn",
        ["organization_id", "observation_id", "turn_index"],
    )
    op.create_index(
        "ix_ingestion_source_turn_source_id",
        "ingestion_source_turn",
        ["organization_id", "source_turn_id"],
    )

    op.create_table(
        "ingestion_attempt",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "observation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ingestion_observation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="processing"),
        sa.Column("worker_id", sa.String(255), nullable=True),
        sa.Column("lease_token", UUID(as_uuid=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_type", sa.String(200), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "observation_id",
            "attempt_number",
            name="uq_ingestion_attempt_observation_number",
        ),
    )
    op.create_index(
        "ix_ingestion_attempt_org_id",
        "ingestion_attempt",
        ["organization_id"],
    )
    op.create_index(
        "ix_ingestion_attempt_observation",
        "ingestion_attempt",
        ["organization_id", "observation_id", "attempt_number"],
    )
    op.create_index(
        "ix_ingestion_attempt_status",
        "ingestion_attempt",
        ["organization_id", "status", "started_at"],
    )

    op.create_table(
        "ingestion_dead_letter",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "observation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ingestion_observation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "attempt_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ingestion_attempt.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("error_type", sa.String(200), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", JSONB(), nullable=True),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "observation_id",
            name="uq_ingestion_dead_letter_observation",
        ),
    )
    op.create_index(
        "ix_ingestion_dead_letter_org_id",
        "ingestion_dead_letter",
        ["organization_id"],
    )
    op.create_index(
        "ix_ingestion_dead_letter_failed_at",
        "ingestion_dead_letter",
        ["organization_id", "failed_at"],
    )

    op.create_table(
        "ingestion_outbox_event",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "observation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ingestion_observation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "attempt_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ingestion_attempt.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "event_type",
            sa.String(100),
            nullable=False,
            server_default="observation.accepted",
        ),
        sa.Column("event_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(255), nullable=True),
        sa.Column("lease_token", UUID(as_uuid=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "event_key",
            name="uq_ingestion_outbox_event_org_key",
        ),
    )
    op.create_index(
        "ix_ingestion_outbox_event_org_id",
        "ingestion_outbox_event",
        ["organization_id"],
    )
    op.create_index(
        "ix_ingestion_outbox_event_dispatch",
        "ingestion_outbox_event",
        ["organization_id", "status", "available_at", "lease_until", "created_at"],
    )
    op.create_index(
        "ix_ingestion_outbox_event_observation",
        "ingestion_outbox_event",
        ["organization_id", "observation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ingestion_outbox_event_observation",
        table_name="ingestion_outbox_event",
    )
    op.drop_index(
        "ix_ingestion_outbox_event_dispatch",
        table_name="ingestion_outbox_event",
    )
    op.drop_index(
        "ix_ingestion_outbox_event_org_id",
        table_name="ingestion_outbox_event",
    )
    op.drop_table("ingestion_outbox_event")

    op.drop_index(
        "ix_ingestion_dead_letter_failed_at",
        table_name="ingestion_dead_letter",
    )
    op.drop_index(
        "ix_ingestion_dead_letter_org_id",
        table_name="ingestion_dead_letter",
    )
    op.drop_table("ingestion_dead_letter")

    op.drop_index("ix_ingestion_attempt_status", table_name="ingestion_attempt")
    op.drop_index(
        "ix_ingestion_attempt_observation",
        table_name="ingestion_attempt",
    )
    op.drop_index("ix_ingestion_attempt_org_id", table_name="ingestion_attempt")
    op.drop_table("ingestion_attempt")

    op.drop_index(
        "ix_ingestion_source_turn_source_id",
        table_name="ingestion_source_turn",
    )
    op.drop_index(
        "ix_ingestion_source_turn_observation",
        table_name="ingestion_source_turn",
    )
    op.drop_index(
        "ix_ingestion_source_turn_org_id",
        table_name="ingestion_source_turn",
    )
    op.drop_table("ingestion_source_turn")

    op.drop_index("ix_ingestion_observation_lease", table_name="ingestion_observation")
    op.drop_index(
        "ix_ingestion_observation_dispatch",
        table_name="ingestion_observation",
    )
    op.drop_index(
        "ix_ingestion_observation_org_id",
        table_name="ingestion_observation",
    )
    op.drop_table("ingestion_observation")

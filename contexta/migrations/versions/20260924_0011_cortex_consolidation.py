from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consolidated_observation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("observation_type", sa.String(32), nullable=False, server_default="fact"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "structured_data",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("risk_tier", sa.String(16), nullable=False, server_default="low"),
        sa.Column("admission_state", sa.String(32), nullable=False, server_default="review"),
        sa.Column("validation_state", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("status", sa.String(32), nullable=False, server_default="staged"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "evidence_ids",
            ARRAY(UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "supporting_ids",
            ARRAY(UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "source_observation_ids",
            ARRAY(UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "fact_keys",
            ARRAY(sa.String(255)),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "evidence_refs",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column(
            "applied_memory_id",
            UUID(as_uuid=True),
            sa.ForeignKey("memory_record.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
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
            name="uq_consolidated_observation_org_idempotency",
        ),
    )
    op.create_index(
        "ix_consolidated_observation_org_id",
        "consolidated_observation",
        ["organization_id"],
    )
    op.create_index(
        "ix_consolidated_observation_org_user_state",
        "consolidated_observation",
        ["organization_id", "user_id", "validation_state"],
    )
    op.create_index(
        "ix_consolidated_observation_supporting_ids",
        "consolidated_observation",
        ["supporting_ids"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_consolidated_observation_evidence_ids",
        "consolidated_observation",
        ["evidence_ids"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_consolidated_observation_fact_keys",
        "consolidated_observation",
        ["fact_keys"],
        postgresql_using="gin",
    )

    op.create_table(
        "memory_proposal",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "consolidated_observation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("consolidated_observation.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("proposal_type", sa.String(32), nullable=False),
        sa.Column("risk_tier", sa.String(16), nullable=False),
        sa.Column("validation_state", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("admission_state", sa.String(32), nullable=False, server_default="review"),
        sa.Column("status", sa.String(32), nullable=False, server_default="proposed"),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column(
            "payload",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "evidence_ids",
            ARRAY(UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "fact_keys",
            ARRAY(sa.String(255)),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "supporting_ids",
            ARRAY(UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "source_observation_ids",
            ARRAY(UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "target_memory_ids",
            ARRAY(UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "evidence_refs",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "validation_errors",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column(
            "canonical_memory_id",
            UUID(as_uuid=True),
            sa.ForeignKey("memory_record.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
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
            name="uq_memory_proposal_org_idempotency",
        ),
    )
    op.create_index("ix_memory_proposal_org_id", "memory_proposal", ["organization_id"])
    op.create_index(
        "ix_memory_proposal_org_user_state",
        "memory_proposal",
        ["organization_id", "user_id", "validation_state"],
    )
    op.create_index(
        "ix_memory_proposal_org_admission",
        "memory_proposal",
        ["organization_id", "admission_state", "risk_tier"],
    )
    op.create_index(
        "ix_memory_proposal_evidence_ids",
        "memory_proposal",
        ["evidence_ids"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_memory_proposal_fact_keys",
        "memory_proposal",
        ["fact_keys"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_memory_proposal_fact_keys", table_name="memory_proposal")
    op.drop_index("ix_memory_proposal_evidence_ids", table_name="memory_proposal")
    op.drop_index("ix_memory_proposal_org_admission", table_name="memory_proposal")
    op.drop_index("ix_memory_proposal_org_user_state", table_name="memory_proposal")
    op.drop_index("ix_memory_proposal_org_id", table_name="memory_proposal")
    op.drop_table("memory_proposal")
    op.drop_index(
        "ix_consolidated_observation_fact_keys",
        table_name="consolidated_observation",
    )
    op.drop_index(
        "ix_consolidated_observation_evidence_ids",
        table_name="consolidated_observation",
    )
    op.drop_index(
        "ix_consolidated_observation_supporting_ids",
        table_name="consolidated_observation",
    )
    op.drop_index(
        "ix_consolidated_observation_org_user_state",
        table_name="consolidated_observation",
    )
    op.drop_index(
        "ix_consolidated_observation_org_id",
        table_name="consolidated_observation",
    )
    op.drop_table("consolidated_observation")

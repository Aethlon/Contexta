from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.Uuid:
    return UUID(as_uuid=True)


def _now() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def _json_metadata() -> sa.Column:
    return sa.Column("metadata", JSONB(), nullable=True)


def upgrade() -> None:
    op.create_table(
        "memory_user",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            _uuid(),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            _uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("attributes", JSONB(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        _json_metadata(),
        _now(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "external_id",
            name="uq_memory_user_org_external_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "account_id",
            name="uq_memory_user_org_account",
        ),
    )
    op.create_index("ix_memory_user_organization_id", "memory_user", ["organization_id"])
    op.create_index("ix_memory_user_account_id", "memory_user", ["account_id"])
    op.create_index(
        "ix_memory_user_org_account",
        "memory_user",
        ["organization_id", "account_id"],
    )
    op.create_index(
        "ix_memory_user_org_status",
        "memory_user",
        ["organization_id", "status"],
    )

    op.create_table(
        "agent",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            _uuid(),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            _uuid(),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            _uuid(),
            sa.ForeignKey("project.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column(
            "agent_type",
            sa.String(50),
            nullable=False,
            server_default="assistant",
        ),
        sa.Column("model_name", sa.String(200), nullable=True),
        sa.Column("model_version", sa.String(255), nullable=True),
        sa.Column("config", JSONB(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        _json_metadata(),
        _now(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("organization_id", "slug", name="uq_agent_org_slug"),
    )
    op.create_index("ix_agent_organization_id", "agent", ["organization_id"])
    op.create_index("ix_agent_account_id", "agent", ["account_id"])
    op.create_index("ix_agent_project_id", "agent", ["project_id"])
    op.create_index("ix_agent_org_project", "agent", ["organization_id", "project_id"])
    op.create_index("ix_agent_org_account", "agent", ["organization_id", "account_id"])
    op.create_index("ix_agent_org_status", "agent", ["organization_id", "status"])

    op.create_table(
        "session_scope",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            _uuid(),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            _uuid(),
            sa.ForeignKey("session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            _uuid(),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "memory_user_id",
            _uuid(),
            sa.ForeignKey("memory_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_id", _uuid(), nullable=True),
        sa.Column(
            "agent_id",
            _uuid(),
            sa.ForeignKey("agent.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            _uuid(),
            sa.ForeignKey("project.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        _json_metadata(),
        _now(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "session_id",
            name="uq_session_scope_org_session",
        ),
    )
    op.create_index("ix_session_scope_organization_id", "session_scope", ["organization_id"])
    op.create_index("ix_session_scope_session_id", "session_scope", ["session_id"])
    op.create_index(
        "ix_session_scope_org_agent",
        "session_scope",
        ["organization_id", "agent_id"],
    )
    op.create_index(
        "ix_session_scope_org_project",
        "session_scope",
        ["organization_id", "project_id"],
    )
    op.create_index(
        "ix_session_scope_org_user",
        "session_scope",
        ["organization_id", "user_id"],
    )

    op.create_table(
        "episode",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            _uuid(),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            _uuid(),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "memory_user_id",
            _uuid(),
            sa.ForeignKey("memory_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_id", _uuid(), nullable=True),
        sa.Column(
            "agent_id",
            _uuid(),
            sa.ForeignKey("agent.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            _uuid(),
            sa.ForeignKey("project.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "session_id",
            _uuid(),
            sa.ForeignKey("session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("episode_key", sa.String(255), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "source_authority",
            sa.String(100),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "source_origin",
            sa.String(255),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("model_version", sa.String(255), nullable=True),
        _json_metadata(),
        _now(),
        sa.UniqueConstraint(
            "organization_id",
            "episode_key",
            name="uq_episode_org_key",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "external_id",
            name="uq_episode_org_external_id",
        ),
    )
    op.create_index("ix_episode_organization_id", "episode", ["organization_id"])
    op.create_index(
        "ix_episode_org_session",
        "episode",
        ["organization_id", "session_id"],
    )
    op.create_index(
        "ix_episode_org_user_occurred",
        "episode",
        ["organization_id", "user_id", "occurred_at"],
    )
    op.create_index("ix_episode_org_external", "episode", ["organization_id", "external_id"])
    op.create_index("ix_episode_org_key", "episode", ["organization_id", "episode_key"])
    op.create_index("ix_episode_org_recorded", "episode", ["organization_id", "recorded_at"])

    op.create_table(
        "source_turn",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            _uuid(),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "episode_id",
            _uuid(),
            sa.ForeignKey("episode.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            _uuid(),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "memory_user_id",
            _uuid(),
            sa.ForeignKey("memory_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_id", _uuid(), nullable=True),
        sa.Column(
            "agent_id",
            _uuid(),
            sa.ForeignKey("agent.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            _uuid(),
            sa.ForeignKey("project.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "session_id",
            _uuid(),
            sa.ForeignKey("session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("source_turn_id", sa.String(255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source_authority",
            sa.String(100),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "source_origin",
            sa.String(255),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("model_version", sa.String(255), nullable=True),
        _json_metadata(),
        _now(),
        sa.UniqueConstraint(
            "episode_id",
            "turn_index",
            name="uq_source_turn_episode_index",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "source_turn_id",
            name="uq_source_turn_org_source_id",
        ),
        sa.CheckConstraint("turn_index >= 0", name="ck_source_turn_turn_index_nonnegative"),
    )
    op.create_index("ix_source_turn_organization_id", "source_turn", ["organization_id"])
    op.create_index("ix_source_turn_episode_id", "source_turn", ["episode_id"])
    op.create_index(
        "ix_source_turn_org_source_id",
        "source_turn",
        ["organization_id", "source_turn_id"],
    )
    op.create_index(
        "ix_source_turn_org_episode",
        "source_turn",
        ["organization_id", "episode_id", "turn_index"],
    )

    op.create_table(
        "memory_fact",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            _uuid(),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            _uuid(),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "memory_user_id",
            _uuid(),
            sa.ForeignKey("memory_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_id", _uuid(), nullable=False),
        sa.Column(
            "agent_id",
            _uuid(),
            sa.ForeignKey("agent.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            _uuid(),
            sa.ForeignKey("project.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "session_id",
            _uuid(),
            sa.ForeignKey("session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "episode_id",
            _uuid(),
            sa.ForeignKey("episode.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("subject", sa.String(1000), nullable=False),
        sa.Column("predicate", sa.String(255), nullable=False),
        sa.Column("object", sa.Text(), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("value_type", sa.String(32), nullable=False, server_default="string"),
        sa.Column("fact_key", sa.String(512), nullable=False),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "known_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "source_authority",
            sa.String(100),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "source_origin",
            sa.String(255),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("model_version", sa.String(255), nullable=True),
        sa.Column("source_id", sa.String(255), nullable=True),
        sa.Column("source_message_id", sa.String(255), nullable=True),
        sa.Column("lineage_id", sa.String(128), nullable=True),
        sa.Column(
            "superseded_by_id",
            _uuid(),
            sa.ForeignKey("memory_fact.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        _json_metadata(),
        _now(),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_memory_fact_valid_range",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_memory_fact_confidence_range",
        ),
        sa.CheckConstraint(
            "importance >= 0 AND importance <= 1",
            name="ck_memory_fact_importance_range",
        ),
    )
    op.create_index("ix_memory_fact_organization_id", "memory_fact", ["organization_id"])
    op.create_index("ix_memory_fact_user_id", "memory_fact", ["user_id"])
    op.create_index("ix_memory_fact_fact_key", "memory_fact", ["fact_key"])
    op.create_index(
        "ix_memory_fact_org_fact_key",
        "memory_fact",
        ["organization_id", "fact_key"],
    )
    op.create_index(
        "ix_memory_fact_org_user_fact_key",
        "memory_fact",
        ["organization_id", "user_id", "fact_key"],
    )
    op.create_index(
        "ix_memory_fact_org_subject_predicate",
        "memory_fact",
        ["organization_id", "subject", "predicate"],
    )
    op.create_index(
        "ix_memory_fact_org_validity",
        "memory_fact",
        ["organization_id", "user_id", "valid_from", "valid_to"],
    )
    op.create_index(
        "ix_memory_fact_org_source",
        "memory_fact",
        ["organization_id", "source_authority", "source_origin"],
    )

    op.create_table(
        "memory_evidence",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            _uuid(),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            _uuid(),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "memory_user_id",
            _uuid(),
            sa.ForeignKey("memory_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_id", _uuid(), nullable=True),
        sa.Column(
            "agent_id",
            _uuid(),
            sa.ForeignKey("agent.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            _uuid(),
            sa.ForeignKey("project.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "session_id",
            _uuid(),
            sa.ForeignKey("session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "episode_id",
            _uuid(),
            sa.ForeignKey("episode.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_turn_id",
            _uuid(),
            sa.ForeignKey("source_turn.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "observation_id",
            _uuid(),
            sa.ForeignKey("ingestion_observation.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "fact_id",
            _uuid(),
            sa.ForeignKey("memory_fact.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("evidence_key", sa.String(255), nullable=True),
        sa.Column(
            "evidence_type",
            sa.String(50),
            nullable=False,
            server_default="source_turn",
        ),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("locator", sa.String(1024), nullable=True),
        sa.Column("source_id", sa.String(255), nullable=True),
        sa.Column("source_message_id", sa.String(255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "source_authority",
            sa.String(100),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "source_origin",
            sa.String(255),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("model_version", sa.String(255), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        _json_metadata(),
        _now(),
        sa.UniqueConstraint(
            "organization_id",
            "evidence_key",
            name="uq_memory_evidence_org_key",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_memory_evidence_confidence_range",
        ),
    )
    op.create_index("ix_memory_evidence_organization_id", "memory_evidence", ["organization_id"])
    op.create_index("ix_memory_evidence_episode_id", "memory_evidence", ["episode_id"])
    op.create_index("ix_memory_evidence_source_turn_id", "memory_evidence", ["source_turn_id"])
    op.create_index("ix_memory_evidence_fact_id", "memory_evidence", ["fact_id"])
    op.create_index("ix_memory_evidence_org_fact", "memory_evidence", ["organization_id", "fact_id"])
    op.create_index(
        "ix_memory_evidence_org_episode",
        "memory_evidence",
        ["organization_id", "episode_id"],
    )
    op.create_index(
        "ix_memory_evidence_org_turn",
        "memory_evidence",
        ["organization_id", "source_turn_id"],
    )
    op.create_index(
        "ix_memory_evidence_org_observation",
        "memory_evidence",
        ["organization_id", "observation_id"],
    )

    op.create_table(
        "memory_block",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            _uuid(),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            _uuid(),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "memory_user_id",
            _uuid(),
            sa.ForeignKey("memory_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_id", _uuid(), nullable=True),
        sa.Column(
            "agent_id",
            _uuid(),
            sa.ForeignKey("agent.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            _uuid(),
            sa.ForeignKey("project.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "session_id",
            _uuid(),
            sa.ForeignKey("session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("block_key", sa.String(255), nullable=False),
        sa.Column("block_type", sa.String(50), nullable=False, server_default="memory"),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("structured_data", JSONB(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("current_revision_id", _uuid(), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("model_version", sa.String(255), nullable=True),
        sa.Column(
            "source_authority",
            sa.String(100),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "source_origin",
            sa.String(255),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        _json_metadata(),
        _now(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("organization_id", "block_key", name="uq_memory_block_org_key"),
        sa.CheckConstraint(
            "current_version >= 0",
            name="ck_memory_block_current_version_nonnegative",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_memory_block_valid_range",
        ),
    )
    op.create_index("ix_memory_block_organization_id", "memory_block", ["organization_id"])
    op.create_index(
        "ix_memory_block_org_scope",
        "memory_block",
        ["organization_id", "memory_user_id", "agent_id"],
    )
    op.create_index("ix_memory_block_org_project", "memory_block", ["organization_id", "project_id"])
    op.create_index("ix_memory_block_org_current", "memory_block", ["organization_id", "current_revision_id"])
    op.create_index("ix_memory_block_org_type", "memory_block", ["organization_id", "block_type", "status"])

    op.create_table(
        "memory_block_revision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            _uuid(),
            sa.ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "block_id",
            _uuid(),
            sa.ForeignKey("memory_block.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            _uuid(),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "memory_user_id",
            _uuid(),
            sa.ForeignKey("memory_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_id", _uuid(), nullable=True),
        sa.Column(
            "agent_id",
            _uuid(),
            sa.ForeignKey("agent.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            _uuid(),
            sa.ForeignKey("project.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "session_id",
            _uuid(),
            sa.ForeignKey("session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_data", JSONB(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("model_version", sa.String(255), nullable=True),
        sa.Column(
            "source_authority",
            sa.String(100),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "source_origin",
            sa.String(255),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column(
            "created_by",
            _uuid(),
            sa.ForeignKey("account.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "supersedes_revision_id",
            _uuid(),
            sa.ForeignKey("memory_block_revision.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        _json_metadata(),
        _now(),
        sa.UniqueConstraint(
            "block_id",
            "revision_number",
            name="uq_memory_block_revision_number",
        ),
        sa.CheckConstraint(
            "revision_number > 0",
            name="ck_memory_block_revision_number_positive",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_memory_block_revision_valid_range",
        ),
    )
    op.create_index("ix_memory_block_revision_organization_id", "memory_block_revision", ["organization_id"])
    op.create_index("ix_memory_block_revision_block_id", "memory_block_revision", ["block_id"])
    op.create_index(
        "ix_memory_block_revision_org_block",
        "memory_block_revision",
        ["organization_id", "block_id", "revision_number"],
    )
    op.create_index(
        "ix_memory_block_revision_org_hash",
        "memory_block_revision",
        ["organization_id", "content_hash"],
    )
    op.create_index(
        "ix_memory_block_revision_org_created",
        "memory_block_revision",
        ["organization_id", "created_at"],
    )
    op.create_foreign_key(
        "fk_memory_block_current_revision_id_memory_block_revision",
        "memory_block",
        "memory_block_revision",
        ["current_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_memory_block_current_revision_id_memory_block_revision",
        "memory_block",
        type_="foreignkey",
    )
    op.drop_table("memory_block_revision")
    op.drop_table("memory_block")
    op.drop_table("memory_evidence")
    op.drop_table("memory_fact")
    op.drop_table("source_turn")
    op.drop_table("episode")
    op.drop_table("session_scope")
    op.drop_table("agent")
    op.drop_table("memory_user")

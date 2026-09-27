"""Drop the billing tables and the six dead domain schemas.

Revision ID: 020
Revises: 019
Create Date: 2026-09-26

Two families of table are removed. Both are removed because a repo-wide grep
found no reader anywhere outside tests, migrations, and prose.

1. Billing / usage metering -- 18 physical tables created by revision 003:
   ``usage_event`` (a RANGE-partitioned parent), its 15 monthly partitions
   ``usage_event_2026_01`` .. ``usage_event_2027_03``, plus ``usage_daily``
   and ``usage_period`` (the latter carrying ``overage_cents`` and
   ``invoice_id``). These contradict AGENTS.md invariant E -- "Billing and
   usage metering have been permanently excised from Contexta Core. Do not
   re-introduce Stripe/Dodo checkout, billing webhooks, or credit deduction
   middleware." The Python surface was already excised
   (``contexta/models/usage.py``, ``contexta/api/routes/billing.py``,
   ``contexta/services/dodo_billing.py`` and the Go aggregator were all
   deleted); revision 003 was the last remaining thing still creating these
   tables. ``docs/OSS_CORE_PLAN.md`` recorded the leftover as "squash later".

2. Six dead domain schemas created by revision 001: ``semantic_cluster``,
   ``cluster_membership``, ``compressed_summary``, ``retrieval_feedback``,
   ``memory_policy`` and ``custom_schema``. Each is reachable only from a dead
   engine module under ``contexta/core/`` that is itself imported only by
   tests. ``retrieval_feedback`` in particular is dead even though feedback is
   a live feature: the live ``POST /memories/{id}/feedback`` route calls
   ``MemoryRepository.apply_feedback``, which mutates
   ``memory_record.utility_score``/``confidence`` and never touches the table.

``compressed_summary`` and ``missing_memory_candidate`` are NOT dropped here --
revision 018 repoints them and owns them. The vestigial billing columns on
``organization`` (``plan_code``, ``dodo_customer_id``,
``dodo_subscription_id``) are also left alone: dropping columns is a different
risk class from dropping whole dead tables.

This migration drops the TABLES ONLY. The ORM models under
``contexta/models/`` (``SemanticCluster``, ``ClusterMembership``,
``CompressedSummary``, ``RetrievalFeedback``, ``MemoryPolicy``,
``CustomSchema``) and their five dead engine modules are deliberately left in
place; removing them is a separate, coordinated change. Until it lands,
``Base.metadata`` still describes these dropped tables, which will break
``alembic revision --autogenerate`` and any test that calls ``create_all()``.

The downgrade recreates the original shape faithfully -- columns, types,
nullability, defaults, constraint and index names, the RANGE partitioning and
all 15 partitions -- copied from revisions 003 and 001 rather than
reconstructed. It exists only for symmetry with the upgrade and to keep the
Alembic chain reversible; no code in this repository reads any of these
tables, so nothing needs them back.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import BIGINT, JSONB, UUID

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


# The (year, month) pairs revision 003 looped over to build the monthly
# partitions of `usage_event`. Copied verbatim so the downgrade restores the
# same 15 partitions over the same ranges.
_USAGE_EVENT_PARTITIONS: tuple[tuple[int, int], ...] = (
    (2026, 1), (2026, 2), (2026, 3), (2026, 4), (2026, 5), (2026, 6),
    (2026, 7), (2026, 8), (2026, 9), (2026, 10), (2026, 11), (2026, 12),
    (2027, 1), (2027, 2), (2027, 3),
)

# Dropped in this order. `cluster_membership` must precede `semantic_cluster`
# because it holds an FK to it; dropping the child first means the parent
# needs no CASCADE. Nothing outside this list references any of these tables,
# so every drop below is a plain DROP and an unexpected new dependency will
# fail the migration loudly instead of silently cascading away live data.
_DEAD_TABLES: tuple[str, ...] = (
    "cluster_membership",
    "semantic_cluster",
    "compressed_summary",
    "retrieval_feedback",
    "memory_policy",
    "custom_schema",
)


def _partition_name(year: int, month: int) -> str:
    return f"usage_event_{year}_{month:02d}"


def _partition_names() -> tuple[str, ...]:
    return tuple(_partition_name(y, m) for y, m in _USAGE_EVENT_PARTITIONS)


def _report_unlisted_partitions() -> None:
    """Print any attached partition that is not in the known list of 15.

    `usage_event` is dropped with CASCADE because a partitioned parent cannot
    be dropped while partitions are attached to it. By this point the 15 known
    partitions have already been dropped by name, so the only thing CASCADE can
    still take is a partition created outside revision 003. Logging it turns a
    would-be silent data loss into a visible one.
    """
    known = set(_partition_names())
    attached = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT child.relname
                FROM pg_inherits i
                JOIN pg_class child ON child.oid = i.inhrelid
                JOIN pg_class parent ON parent.oid = i.inhparent
                WHERE parent.relname = 'usage_event'
                ORDER BY child.relname
                """
            )
        )
        .scalars()
        .all()
    )
    for name in attached:
        if name not in known:
            print(
                f"020: WARNING: DROP TABLE usage_event CASCADE will also drop "
                f"partition {name!r}, which revision 003 did not create"
            )


def upgrade() -> None:
    # --- billing: partitions by name, then the partitioned parent ---
    for name in _partition_names():
        op.execute(f"DROP TABLE IF EXISTS {name}")

    # CASCADE is required here only for the parent/partition attachment. Every
    # object it can reach is enumerated by _report_unlisted_partitions() above
    # and the 15 named partitions are already gone by this point.
    _report_unlisted_partitions()
    op.execute("DROP TABLE IF EXISTS usage_event CASCADE")

    op.execute("DROP TABLE IF EXISTS usage_daily")
    op.execute("DROP TABLE IF EXISTS usage_period")

    # --- dead domain schemas, children before parents ---
    for table in _DEAD_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")


def downgrade() -> None:
    # =====================================================================
    # Billing -- recreated in the exact order revision 003 created it:
    # parent, 15 partitions, then the two indexes on the parent, then
    # usage_daily, then usage_period.
    # =====================================================================
    op.execute(
        """
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
        """
    )

    for year, month in _USAGE_EVENT_PARTITIONS:
        start = f"{year}-{month:02d}-01"
        end_year = year + (month // 12)
        end_month = (month % 12) + 1
        end = f"{end_year}-{end_month:02d}-01"
        op.execute(
            f"""
            CREATE TABLE {_partition_name(year, month)} PARTITION OF usage_event
            FOR VALUES FROM ('{start}') TO ('{end}')
            """
        )

    op.create_index(
        "ix_usage_event_org_occurred", "usage_event", ["organization_id", "occurred_at"]
    )
    op.create_index(
        "ix_usage_event_org_classification",
        "usage_event",
        ["organization_id", "classification"],
    )

    op.create_table(
        "usage_daily",
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        # Declared nullable in revision 003 but part of the composite primary
        # key, so PostgreSQL promotes it to NOT NULL. Recreated the same way
        # so the restored nullability matches the original exactly.
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
        sa.PrimaryKeyConstraint(
            "organization_id", "project_id", "day", "classification",
            name="pk_usage_daily",
        ),
    )

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
        sa.PrimaryKeyConstraint(
            "organization_id", "period_start", name="pk_usage_period"
        ),
    )

    # =====================================================================
    # Dead domain schemas -- recreated in the exact order revision 001
    # created them. Constraint and index names are given explicitly so the
    # restore is deterministic rather than dependent on the metadata naming
    # convention being plumbed through the migration context.
    # =====================================================================
    op.create_table(
        "retrieval_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "memory_id",
            sa.Uuid(),
            sa.ForeignKey(
                "memory_record.id",
                name="fk_retrieval_feedback_memory_id_memory_record",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey(
                "session.id",
                name="fk_retrieval_feedback_session_id_session",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        sa.Column("context_request_id", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("signal", sa.String(20), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_retrieval_feedback"),
    )
    op.create_index(
        "ix_retrieval_feedback_memory_signal",
        "retrieval_feedback",
        ["memory_id", "signal"],
    )

    op.create_table(
        "memory_policy",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("store_rules", JSONB, nullable=True),
        sa.Column("ignore_rules", JSONB, nullable=True),
        sa.Column("priority_weights", JSONB, nullable=True),
        sa.Column(
            "is_builtin", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_memory_policy"),
    )

    op.create_table(
        "custom_schema",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("field_definitions", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_custom_schema"),
    )

    op.create_table(
        "semantic_cluster",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_semantic_cluster"),
    )

    # No organization_id column, and therefore no tenant isolation at all --
    # one of the reasons this table is going.
    op.create_table(
        "cluster_membership",
        sa.Column(
            "cluster_id",
            sa.Uuid(),
            sa.ForeignKey(
                "semantic_cluster.id",
                name="fk_cluster_membership_cluster_id_semantic_cluster",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "memory_id",
            sa.Uuid(),
            sa.ForeignKey(
                "memory_record.id",
                name="fk_cluster_membership_memory_id_memory_record",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint(
            "cluster_id", "memory_id", name="pk_cluster_membership"
        ),
    )

    op.create_table(
        "compressed_summary",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "entity_id",
            sa.Uuid(),
            sa.ForeignKey(
                "entity.id",
                name="fk_compressed_summary_entity_id_entity",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("key_facts", JSONB, nullable=True),
        sa.Column(
            "confidence", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column(
            "source_memory_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "is_stale", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_compressed_summary"),
    )

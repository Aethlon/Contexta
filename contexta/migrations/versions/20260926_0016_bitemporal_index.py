"""Bitemporal range index for memory_record.

Phase 1 made `as_of` a real SQL predicate on the memory search paths
(`MemoryRepository._apply_as_of_filter`), mirroring the half-open validity
window `MemoryFactRepository.get_by_fact_key` already used. That turned the
"what was true at T" question into a range scan on `valid_from`.

`memory_fact` already carries the matching index (`ix_memory_fact_org_validity`
on `(organization_id, user_id, valid_from, valid_to)`), but `memory_record` had
no index leading with a temporal column at all -- `valid_from` was unindexed
everywhere, and `event_at` only ever appeared third. On the reference data set
the as-of predicate degraded to a bitmap scan over every candidate row for the
tenant (40,202 index entries for a single user) or a sequential scan when
`user_id` was absent.

This adds the one missing index. It is built CONCURRENTLY because
`memory_record` is the largest table in the schema.
"""

from __future__ import annotations

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_memory_record_org_validity"
TABLE_NAME = "memory_record"
COLUMNS = ["organization_id", "user_id", "valid_from", "valid_to"]


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
            f"ON {TABLE_NAME} ({', '.join(COLUMNS)})"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}")

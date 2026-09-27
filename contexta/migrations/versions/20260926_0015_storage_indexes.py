"""Storage and knowledge-graph indexes for the hot retrieval paths.

Adds the indexes the hybrid retrieval engine, the truth engine and the graph
walk actually filter on, and reworks two indexes that were structurally
unable to serve their queries:

* `ix_memory_record_org_valid_to_partial` carried `valid_to` as its second
  key column. Every row in a partial index built on `valid_to IS NULL` has
  `valid_to = NULL`, so that column was constant and carried zero
  information -- the index was equivalent to a plain index on
  `organization_id`. It is rebuilt on `(organization_id, user_id)`, the
  real tenant + subject prefix that every scoped read filters on.
* `memory_entity_link` had no index leading with `entity_id`, so the
  `WHERE entity_id = ?` graph-expansion query could not use its
  `(memory_id, entity_id)` primary key at all: `entity_id` was the second
  key column and unusable as a leading prefix.

`entity_edge` gains a uniqueness constraint and a no-self-loop check, so
duplicates and self-loops are cleaned first. Self-loops are meaningless and
`_create_supersession_edges` in the truth engine no longer emits them, but
historical rows may still contain some.

Locking notes:
* CONCURRENTLY-capable and run outside a transaction below: every
  `memory_record` index build, plus the `entity` trigram index. These run
  inside `autocommit_block()` because `CREATE INDEX CONCURRENTLY` is
  rejected inside a transaction block.
* NOT concurrently-capable, so they run in the normal transaction:
  `DROP INDEX` (catalog-only; it takes ACCESS EXCLUSIVE on the index, not on
  the table, and returns without scanning), and both `ALTER TABLE ... ADD
  CONSTRAINT` statements (PostgreSQL has no `IF NOT EXISTS` for constraints;
  `entity_edge` is small, so the brief ACCESS EXCLUSIVE lock is acceptable).
  `ADD CONSTRAINT ... UNIQUE` could be made non-blocking by first building a
  unique index CONCURRENTLY and attaching it, but that is not worth the
  complexity at this table size.
* `CREATE EXTENSION IF NOT EXISTS pg_trgm` is a guarded no-op: revision 001
  already installed it, but the trigram index below would fail on a database
  restored without it.

`op.create_check_constraint` and `op.drop_constraint` both build their
`Table` against `Base.metadata`, so the `ck` naming convention
(`ck_%(table_name)s_%(constraint_name)s`) rewrites whatever name they are
given. The check constraint is therefore declared as `no_self_loop` on both
sides of the round trip so it lands in the database as
`ck_entity_edge_no_self_loop`. The `uq` convention does not interpolate
`%(constraint_name)s`, so `uq_entity_edge_identity` passes through as-is.

Note that `autocommit_block()` commits the work that precedes it, so this
migration is only safe to re-run from revision 013 if it failed *before*
the concurrent block. Everything inside the block is `IF [NOT] EXISTS`
guarded; the two `DELETE` cleanups are naturally idempotent because they
re-derive their target set from the current contents.

Revision ID: 015
Revises: 014
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision: str = "015"
down_revision: str | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DELETE_SELF_LOOPS = """
WITH deleted AS (
    DELETE FROM entity_edge
    WHERE source_entity_id = target_entity_id
    RETURNING 1
)
SELECT count(*) FROM deleted
"""

# Keeps the earliest row of every (organization, source, target, relationship)
# group. The row comparison is the "smallest created_at, tie-break on id"
# rule and is strictly greater-than, so running it twice deletes nothing the
# second time. `ix_entity_edge_scoped` and the existing
# `ix_entity_edge_source` / `ix_entity_edge_target` indexes keep this
# self-join bounded.
_DELETE_DUPLICATE_EDGES = """
WITH deleted AS (
    DELETE FROM entity_edge a USING entity_edge b
    WHERE a.organization_id = b.organization_id
      AND a.source_entity_id = b.source_entity_id
      AND a.target_entity_id = b.target_entity_id
      AND a.relationship_type = b.relationship_type
      AND (a.created_at, a.id) > (b.created_at, b.id)
    RETURNING 1
)
SELECT count(*) FROM deleted
"""

_MEMORY_RECORD_CURRENT_INDEXES = (
    (
        "ix_memory_record_event_current",
        "ON memory_record (organization_id, user_id, event_at DESC) "
        "WHERE valid_to IS NULL",
    ),
    (
        "ix_memory_record_created_current",
        "ON memory_record (organization_id, user_id, created_at DESC) "
        "WHERE valid_to IS NULL",
    ),
    (
        "ix_memory_record_fact_key_current",
        "ON memory_record (organization_id, user_id, fact_key) "
        "WHERE valid_to IS NULL",
    ),
    (
        "ix_memory_record_last_accessed",
        "ON memory_record (organization_id, last_accessed_at) "
        "WHERE is_pinned = false AND valid_to IS NULL",
    ),
    ("ix_memory_record_tags_gin", "ON memory_record USING gin (tags)"),
)


def _concurrently_create(index_name: str, definition: str) -> None:
    op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name} {definition}")


def _concurrently_drop(index_name: str) -> None:
    op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")


def _delete_count(bind: Connection, statement: str, label: str) -> int:
    deleted = bind.execute(sa.text(statement)).scalar_one()
    print(f"015: {label}: {deleted} row(s) deleted")
    return deleted


def upgrade() -> None:
    bind = op.get_bind()

    _delete_count(bind, _DELETE_SELF_LOOPS, "entity_edge self-loops removed")
    _delete_count(bind, _DELETE_DUPLICATE_EDGES, "duplicate entity_edge rows removed")

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.drop_index("ix_memory_record_org_valid_to_partial", table_name="memory_record")

    with op.get_context().autocommit_block():
        _concurrently_create(
            "ix_memory_record_org_valid_to_partial",
            "ON memory_record (organization_id, user_id) WHERE valid_to IS NULL",
        )
        for index_name, definition in _MEMORY_RECORD_CURRENT_INDEXES:
            _concurrently_create(index_name, definition)
        _concurrently_create(
            "ix_entity_name_trgm",
            "ON entity USING gin (name gin_trgm_ops)",
        )

    op.create_index(
        "ix_entity_identity",
        "entity",
        ["organization_id", "user_id", sa.text("lower(name)")],
    )
    op.create_index(
        "ix_entity_edge_scoped",
        "entity_edge",
        ["organization_id", "source_entity_id", "target_entity_id"],
    )
    op.create_index(
        "ix_entity_edge_scoped_rev",
        "entity_edge",
        ["organization_id", "target_entity_id", "source_entity_id"],
    )
    op.create_index(
        "ix_mem_entity_link_entity",
        "memory_entity_link",
        ["entity_id", "memory_id"],
    )
    op.create_index(
        "ix_version_memory",
        "memory_version",
        ["memory_id", sa.text("valid_from DESC")],
    )

    op.create_unique_constraint(
        "uq_entity_edge_identity",
        "entity_edge",
        [
            "organization_id",
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
        ],
    )
    op.create_check_constraint(
        # Unprefixed: `contexta.models.base.convention` expands this to
        # `ck_entity_edge_no_self_loop`, matching the model declaration.
        "no_self_loop",
        "entity_edge",
        "source_entity_id <> target_entity_id",
    )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        _concurrently_drop("ix_memory_record_org_valid_to_partial")
        _concurrently_create(
            "ix_memory_record_org_valid_to_partial",
            "ON memory_record (organization_id, valid_to) WHERE valid_to IS NULL",
        )
        for index_name, _ in _MEMORY_RECORD_CURRENT_INDEXES:
            _concurrently_drop(index_name)
        _concurrently_drop("ix_entity_name_trgm")

    op.drop_index("ix_entity_identity", table_name="entity")
    op.drop_index("ix_entity_edge_scoped", table_name="entity_edge")
    op.drop_index("ix_entity_edge_scoped_rev", table_name="entity_edge")
    op.drop_index("ix_mem_entity_link_entity", table_name="memory_entity_link")
    op.drop_index("ix_version_memory", table_name="memory_version")

    op.drop_constraint(
        # Unprefixed for the same reason as the matching `upgrade()` call:
        # the naming convention expands this to `ck_entity_edge_no_self_loop`
        # on both sides of the round trip.
        "no_self_loop",
        "entity_edge",
        type_="check",
    )
    op.drop_constraint(
        "uq_entity_edge_identity", "entity_edge", type_="unique"
    )

"""Single current truth per fact slot, enforced by the database.

`ix_memory_record_fact_key_current` already lets truth maintenance find the
rows occupying a fact slot, but it is a plain index: nothing stopped two current
rows from sharing one slot, so "the current truth" was whatever the application
last wrote rather than something the schema guaranteed. This migration turns
that into `uq_memory_record_current_fact_slot`, a *partial unique* index over
`(organization_id, user_id, fact_key)` restricted to `valid_to IS NULL`, which
is exactly the set retrieval reads. Superseding the older row frees the slot, so
the constraint is what makes supersession mandatory rather than optional.

`fact_key IS NOT NULL` is part of the predicate and not an oversight: the key
is still a text hash for every extraction that carries no structural key, and
`NULL` keys are all "no key" rather than one shared slot, so indexing them would
collapse unrelated memories into a single spurious conflict.

Reconciliation
--------------
Building a unique index fails if the data already violates it, so current rows
that share a slot are closed first: the newest by `valid_from` (ties broken by
the highest id) survives and the others are stamped with `valid_to`, exactly as
truth maintenance would have. That is a data change and it is deliberately not
reversed by `downgrade()`: reopening a row would resurrect a belief the system
has already stopped asserting. The count is printed so the effect is visible in
the migration log.

`memory_version` is *not* written for the closed rows: `content` is encrypted at
rest with a per-tenant key the migration has no access to, so any snapshot it
could write would hold ciphertext that no reader can decrypt. The closed rows
keep their history in the same place the application would have put it.

Locking notes:
* The `UPDATE` runs in the normal transaction; it touches only the duplicate
  rows and takes a row lock on each.
* The index build runs inside `autocommit_block()` because `CREATE INDEX
  CONCURRENTLY` is rejected inside a transaction block. `CONCURRENTLY` keeps the
  `memory_record` table writable for the duration of the build, which matters
  because this migration is applied to a live ingestion table.
* `autocommit_block()` commits the reconciliation before the build, so this
  migration is only safe to re-run from revision 018 if it failed *after* that
  commit. The reconciliation is naturally idempotent: it re-derives its target
  set from the rows that are still current, and the index build is `IF NOT
  EXISTS` guarded.

Revision ID: 019
Revises: 018
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision: str = "019"
down_revision: str | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "uq_memory_record_current_fact_slot"
INDEX_DEFINITION = (
    "ON memory_record (organization_id, user_id, fact_key) "
    "WHERE valid_to IS NULL AND fact_key IS NOT NULL"
)

# Picks the survivor of every (organization, user, fact_key) group of current
# rows: newest valid_from first, and the highest id when two rows claim the same
# instant. `ix_memory_record_fact_key_current` is partial on `valid_to IS NULL`,
# so this scan only visits current rows.
_CLOSE_DUPLICATE_CURRENT_ROWS = """
WITH ranked AS (
    SELECT
        id AS loser_id,
        first_value(id) OVER slot AS winner_id
    FROM memory_record
    WHERE valid_to IS NULL AND fact_key IS NOT NULL
    WINDOW slot AS (
        PARTITION BY organization_id, user_id, fact_key
        ORDER BY valid_from DESC, id DESC
    )
),
losers AS (
    SELECT loser_id, winner_id
    FROM ranked
    WHERE loser_id <> winner_id
),
closed AS (
    UPDATE memory_record m
    SET valid_to = GREATEST(
            m.valid_from,
            COALESCE(
                (SELECT w.valid_from FROM memory_record w WHERE w.id = losers.winner_id),
                m.valid_from
            )
        ),
        updated_at = now()
    FROM losers
    WHERE m.id = losers.loser_id
      AND m.valid_to IS NULL
    RETURNING m.id
)
SELECT count(*) FROM closed
"""


def _close_count(bind: Connection) -> int:
    closed = bind.execute(sa.text(_CLOSE_DUPLICATE_CURRENT_ROWS)).scalar_one()
    print(f"019: duplicate current fact-slot rows closed: {closed}")
    return closed


def upgrade() -> None:
    bind = op.get_bind()

    _close_count(bind)

    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} {INDEX_DEFINITION}"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}")

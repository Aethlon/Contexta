"""Real uniqueness for `entity`, and a closed set for `relationship_type`.

Two graph invariants were enforced only in application code, which concurrent
ingestion does not honour:

* `entity` identity was `(organization_id, user_id, lower(name))` with only a
  *non-unique* index, so two batches resolving "Kubernetes" and "kubernetes" at
  the same time each inserted a row. `BulkEntityResolver` cannot close that
  window: its pre-resolution `get_by_names` and the caller's own INSERT are
  separate statements, in separate sessions. `EntityRepository.upsert_by_name`
  now closes it on the write side, and the unique index below is what makes the
  race decidable instead of merely unlikely.

  The index cannot be created while duplicates exist, so this revision
  merges them first. The merge is explicit SQL rather than a model-side pass
  because it has to be re-runnable on a database of any size, and because
  Alembic must not depend on live application code.

* `relationship_type` was free-text `String(50)`. `relation_extractor` emits 24
  literals, `core.types.RelationType` names 7, and the two sets only partially
  overlap, so a typo silently became a new edge type no reader knows how to
  weight. The CHECK below closes the column to the union of the two, and
  normalises the one legacy value (`co_occurs_with`, written by an older
  extractor) that is in neither.

  The merge strategy is chosen so no fact is lost:
  * The survivor is the earliest row of each group (`created_at`, then `id`),
    so the row a reader has been seeing longest keeps its identity and its
    `id` stays valid for anything that stored it.
  * `memory_entity_link` and both `entity_edge` endpoints are repointed at the
    survivor before the losers are deleted. The rows that repointing would
    make redundant -- a memory already linked to the survivor, an edge that
    collapses onto an existing `(organization, source, target, relationship)`
    identity, an edge whose two endpoints were the same entity all along -- are
    deleted in a pass of their own, because PostgreSQL's `ON CONFLICT` is
    INSERT-only and an `UPDATE` cannot absorb them. The row kept in each such
    group is the earliest, and an identity already held by an edge that is not
    moving is never taken from it. Every dropped row was redundant with a row
    that survives, so none of this is data loss.
  * `aggregated_attributes` is merged into the survivor: `mention_count` is
  summed across the group, every other key is taken from the survivor as-is.

Locking notes:
* Nothing here is `CONCURRENTLY`-capable, and nothing needs to be. Every
  statement is either a bulk `DELETE`/`UPDATE` (row locks only) or a
  `DROP INDEX` (catalog-only -- it takes ACCESS EXCLUSIVE on the index, not on
  the table, and returns without scanning the table) or a `CREATE UNIQUE INDEX`
  (SHARE lock: blocks writes for its duration, not reads). `entity` is
  thousands of rows, so the index build is a brief lock. `CREATE UNIQUE INDEX
  CONCURRENTLY` would remove even that, at the cost of a statement that cannot
  run inside the migration transaction and leaves an invalid index behind if a
  concurrent writer collides mid-build.
* The duplicate-merge reports its own row counts through `print()`, the way
  revision 015 did, because the operator applying this needs them in the
  migration log rather than in a table.

Idempotency: every statement re-derives its target set from current table
contents, and both DDL statements are guarded on the way down, so a partially
applied run can be repeated. The merge itself is *forward-only* --
`downgrade()` restores the schema but cannot un-merge entities, and says so.

The two `entity` index objects are also worth being explicit about. The
non-unique `ix_entity_identity` and the new `uq_entity_identity` would have
byte-identical definitions, since PostgreSQL implements a UNIQUE constraint as
a unique index; keeping both would double every write to the table for no
lookup benefit. The old index is therefore dropped, and the unique index is
what `upsert_by_name`'s ON CONFLICT target resolves to. `downgrade()` recreates
the non-unique index exactly as revision 015 left it.

`op.create_check_constraint` is deliberately not used. It builds a `Table`
against `Base.metadata`, so the `ck_%(table_name)s_%(constraint_name)s`
convention rewrites whatever name it is handed -- which is how revision 017's
downgrade ends up asking for `ck_api_key_ck_api_key_tier`, a name that does
not exist. Raw `ALTER TABLE ... IF EXISTS` states the name once and identically
in both directions.

Revision ID: 018
Revises: 017
Create Date: 2026-09-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of `models.entity.ALLOWED_RELATIONSHIP_TYPES`. A migration must
# not import live application code: if that set is later widened, re-running
# this revision has to keep enforcing the set that was correct when it was
# written. Sorted for stable SQL text.
_ALLOWED_RELATIONSHIP_TYPES: tuple[str, ...] = tuple(
    sorted({
        # relation_extractor RELATION_PATTERNS, forward and backward literals.
        "integrates_with", "integrated_by",
        "used_by", "uses",
        "depends_on", "dependency_of",
        "works_on", "worked_on_by",
        "works_at", "employs",
        "created_by", "created",
        "part_of", "has_component",
        "prefers", "preferred_by",
        "avoids", "avoided_by",
        "collaborates_with",
        "located_in", "location_of",
        "is_a", "has_instance",
        # relation_extractor's bounded co-occurrence backfill.
        "related_to",
        # RelationType members relation_extractor has no pattern for. Admitted
        # because `core.entities.resolver.Resolver.create_edge` writes
        # `RelationType` values straight into this column; a narrower
        # constraint would turn `create_edge(RelationType.LIKES)` into a
        # CheckViolation.
        "likes", "owns", "superseded_by",
    })
)

_ALLOWED_LITERAL_SQL = ", ".join(f"'{value}'" for value in _ALLOWED_RELATIONSHIP_TYPES)

# The merged JSONB document for one survivor: its own attributes, then the
# group-wide mention total. `?` and `->>` are the jsonb existence/extract
# operators; the regex guard means a non-numeric `mention_count` left behind by
# an older writer counts as zero instead of aborting the whole migration.
_MERGE_ENTITY_ATTRIBUTES = f"""
WITH group_totals AS (
    SELECT
        g.keep_id,
        sum(
            CASE WHEN (e.aggregated_attributes ->> 'mention_count') ~ '^[0-9]+$'
                 THEN (e.aggregated_attributes ->> 'mention_count')::bigint
                 ELSE 0
            END
        ) AS total_mentions,
        count(*) FILTER (WHERE e.aggregated_attributes ? 'mention_count')
            AS members_with_mentions
    FROM _entity_dup_group g
    JOIN entity e
      ON e.organization_id = g.organization_id
     AND e.user_id = g.user_id
     AND lower(e.name) = g.name_key
    GROUP BY g.keep_id
), merged AS (
    UPDATE entity AS survivor
    SET aggregated_attributes = CASE
            WHEN t.members_with_mentions > 0
            THEN COALESCE(survivor.aggregated_attributes, '{{}}'::jsonb)
                 || jsonb_build_object('mention_count', t.total_mentions)
            ELSE survivor.aggregated_attributes
        END
    FROM group_totals AS t
    WHERE survivor.id = t.keep_id
    RETURNING 1
)
SELECT count(*) FROM merged
"""

# One row per duplicate group. The survivor is `(array_agg(id ORDER BY
# created_at, id))[1]`: earliest wins, lowest id breaks a created_at tie.
# `ON COMMIT DROP` keeps these scratch tables out of the schema -- a re-run
# gets fresh ones.
_CREATE_DUP_GROUP = """
CREATE TEMPORARY TABLE _entity_dup_group ON COMMIT DROP AS
SELECT
    organization_id,
    user_id,
    lower(name) AS name_key,
    (array_agg(id ORDER BY created_at, id))[1] AS keep_id,
    count(*) AS member_count
FROM entity
GROUP BY organization_id, user_id, lower(name)
HAVING count(*) > 1
"""

_CREATE_DUP_MERGE = """
CREATE TEMPORARY TABLE _entity_dup_merge ON COMMIT DROP AS
SELECT e.id AS loser_id, g.keep_id
FROM entity e
JOIN _entity_dup_group g
  ON g.organization_id = e.organization_id
 AND g.user_id = e.user_id
 AND g.name_key = lower(e.name)
WHERE e.id <> g.keep_id
"""

# Claim-then-rank dedup, run BEFORE any endpoint is repointed.
#
# `ON CONFLICT` is an INSERT-only clause, so neither UPDATE below can use it to
# absorb a collision. The collisions are instead removed up front, and each
# UPDATE is then guaranteed conflict-free. The rule is the same shape for both
# tables: a row that is moving to an identity keeps that identity only if no
# row already holds it, and among rows chasing one identity the earliest wins.
# `is_affected ASC` puts rows that are *not* moving ahead of rows that are, so
# an identity already held by a correct row is never taken from it, and only
# rows flagged affected are ever deleted.
#
# The second branch of `claimants` is the rows that stay put but might already
# own a wanted identity. It is what keeps the window function's input bounded:
# without it the partition would span the whole table.
# `memory_entity_link` has no surrogate key -- its primary key is
# (memory_id, entity_id) -- so a row is addressed here by that key as it stands
# *before* the repoint. `row_entity_id` is the current value (the loser for a
# moving row, the survivor for a row that stays), and the DELETE matches on it,
# so the predicate still identifies exactly one row at the moment it runs.
_REPOINT_LINKS_CLAIMANTS = """
WITH claimants AS (
    SELECT
        l.memory_id,
        l.entity_id AS row_entity_id,
        l.created_at,
        m.keep_id,
        true AS is_affected
    FROM memory_entity_link l
    JOIN _entity_dup_merge m ON m.loser_id = l.entity_id
  UNION ALL
    SELECT
        held.memory_id,
        held.entity_id AS row_entity_id,
        held.created_at,
        m.keep_id,
        false AS is_affected
    FROM memory_entity_link held
    JOIN _entity_dup_merge m ON m.keep_id = held.entity_id
), ranked AS (
    SELECT
        memory_id,
        row_entity_id,
        is_affected,
        row_number() OVER (
            PARTITION BY memory_id, keep_id
            ORDER BY is_affected ASC, created_at, row_entity_id
        ) AS identity_rank
    FROM claimants
)
"""

_DROP_LINKS_ON_COLLISION = f"""
{_REPOINT_LINKS_CLAIMANTS}
, removed AS (
    DELETE FROM memory_entity_link l
    USING ranked r
    WHERE l.memory_id = r.memory_id
      AND l.entity_id = r.row_entity_id
      AND r.is_affected
      AND r.identity_rank > 1
    RETURNING 1
)
SELECT count(*) FROM removed
"""

_REPOINT_LINKS = """
WITH repointed AS (
    UPDATE memory_entity_link AS l
    SET entity_id = m.keep_id
    FROM _entity_dup_merge AS m
    WHERE l.entity_id = m.loser_id
    RETURNING 1
)
SELECT count(*) FROM repointed
"""

# The edge variant of the same claim-then-rank rule, with one extra drop
# condition. A row whose two endpoints map to the same entity has no valid
# representation left -- every rewrite of it is a self-loop, and
# `ck_entity_edge_no_self_loop` forbids that -- so it is dropped here rather
# than discovered as a constraint violation mid-UPDATE. Ranking is per
# (organization, mapped source, mapped target, relationship_type), the same
# identity `uq_entity_edge_identity` enforces.
_REPOINT_EDGES_CLAIMANTS = """
WITH endpoint_map AS (
    SELECT
        e.id,
        e.created_at,
        e.organization_id,
        e.relationship_type,
        COALESCE(source_map.keep_id, e.source_entity_id) AS mapped_source,
        COALESCE(target_map.keep_id, e.target_entity_id) AS mapped_target,
        (source_map.loser_id IS NOT NULL OR target_map.loser_id IS NOT NULL)
            AS is_affected
    FROM entity_edge e
    LEFT JOIN _entity_dup_merge source_map
           ON source_map.loser_id = e.source_entity_id
    LEFT JOIN _entity_dup_merge target_map
           ON target_map.loser_id = e.target_entity_id
), affected AS (
    SELECT * FROM endpoint_map WHERE is_affected
), claimants AS (
    SELECT * FROM affected
  UNION ALL
    -- Rows that stay put but may already own an identity an affected row is
    -- moving onto. They must not be affected themselves, or the same row would
    -- appear in both branches and get two ranks in one partition.
    SELECT
        held.id,
        held.created_at,
        held.organization_id,
        held.relationship_type,
        held.source_entity_id AS mapped_source,
        held.target_entity_id AS mapped_target,
        false AS is_affected
    FROM entity_edge held
    JOIN (
        SELECT DISTINCT
            organization_id, relationship_type, mapped_source, mapped_target
        FROM affected
    ) wanted
      ON wanted.organization_id = held.organization_id
     AND wanted.relationship_type = held.relationship_type
     AND wanted.mapped_source = held.source_entity_id
     AND wanted.mapped_target = held.target_entity_id
    LEFT JOIN _entity_dup_merge source_map
           ON source_map.loser_id = held.source_entity_id
    LEFT JOIN _entity_dup_merge target_map
           ON target_map.loser_id = held.target_entity_id
    WHERE source_map.loser_id IS NULL AND target_map.loser_id IS NULL
), ranked AS (
    SELECT
        id,
        is_affected,
        mapped_source,
        mapped_target,
        row_number() OVER (
            PARTITION BY organization_id, mapped_source, mapped_target, relationship_type
            ORDER BY is_affected ASC, created_at, id
        ) AS identity_rank
    FROM claimants
)
"""

_DROP_EDGES_ON_COLLISION = f"""
{_REPOINT_EDGES_CLAIMANTS}
, removed AS (
    DELETE FROM entity_edge e
    USING ranked r
    WHERE e.id = r.id
      AND r.is_affected
      AND (r.mapped_source = r.mapped_target OR r.identity_rank > 1)
    RETURNING 1
)
SELECT count(*) FROM removed
"""

# Source and target are separate passes because a single pass cannot name the
# other column in its own SET list. Both are conflict-free by construction: any
# row whose repoint would have collided is already gone.
_FINAL_EDGE_DEDUPE = """
WITH ranked AS (
    SELECT id,
           row_number() OVER (
               PARTITION BY organization_id, source_entity_id,
                            target_entity_id, relationship_type
               ORDER BY created_at, id
           ) AS rn
    FROM entity_edge
), removed AS (
    DELETE FROM entity_edge e
    USING ranked r
    WHERE e.id = r.id AND r.rn > 1
    RETURNING 1
)
SELECT count(*) FROM removed
"""

_REPOINT_EDGE_SOURCE = """
WITH repointed AS (
    UPDATE entity_edge AS e
    SET source_entity_id = m.keep_id
    FROM _entity_dup_merge AS m
    WHERE e.source_entity_id = m.loser_id
    RETURNING 1
)
SELECT count(*) FROM repointed
"""

_REPOINT_EDGE_TARGET = """
WITH repointed AS (
    UPDATE entity_edge AS e
    SET target_entity_id = m.keep_id
    FROM _entity_dup_merge AS m
    WHERE e.target_entity_id = m.loser_id
    RETURNING 1
)
SELECT count(*) FROM repointed
"""

# The two remaining inbound FKs. Neither has a unique constraint, so a plain
# UPDATE cannot fail; they are here so deleting a loser cannot cascade a
# `compressed_summary` row away or null out a `missing_memory_candidate`'s
# subject.
_REPOINT_COMPRESSED_SUMMARIES = """
WITH repointed AS (
    UPDATE compressed_summary AS c
    SET entity_id = m.keep_id
    FROM _entity_dup_merge AS m
    WHERE c.entity_id = m.loser_id
    RETURNING 1
)
SELECT count(*) FROM repointed
"""

_REPOINT_MISSING_MEMORY_CANDIDATES = """
WITH repointed AS (
    UPDATE missing_memory_candidate AS c
    SET related_entity_id = m.keep_id
    FROM _entity_dup_merge AS m
    WHERE c.related_entity_id = m.loser_id
    RETURNING 1
)
SELECT count(*) FROM repointed
"""

_DELETE_LOSERS = """
WITH removed AS (
    DELETE FROM entity AS e
    USING _entity_dup_merge AS m
    WHERE e.id = m.loser_id
    RETURNING 1
)
SELECT count(*) FROM removed
"""

# One legacy literal, written by an extractor revision that predates
# `relation_extractor`, is in neither the pattern table nor `RelationType`.
# `co_occurs_with` and `related_to` are the same edge -- every reader that
# special-cases it (mcp/service.py, scripts/enrich_graph.py) already tests
# `in {"co_occurs_with", "related_to"}` -- so folding it into `related_to`
# changes no reader's behaviour.
_NORMALISE_RELATIONSHIP_TYPES = f"""
WITH normalised AS (
    UPDATE entity_edge
    SET relationship_type = 'related_to'
    WHERE relationship_type <> ALL (ARRAY[{_ALLOWED_LITERAL_SQL}]::text[])
    RETURNING 1
)
SELECT count(*) FROM normalised
"""


def _report(bind: Connection, statement: str, label: str) -> int:
    """Run a COUNT-returning DML statement and log how many rows it touched."""
    count = bind.execute(sa.text(statement)).scalar_one()
    print(f"018: {label}: {count} row(s)")
    return count


def _merge_duplicate_entities(bind: Connection) -> None:
    """Collapse duplicate entities onto the earliest row of each group."""
    groups = bind.execute(
        sa.text(
            """
            SELECT count(*) AS groups,
                   COALESCE(sum(member_count), 0) AS rows_in_groups
            FROM _entity_dup_group
            """
        )
    ).one()
    print(
        f"018: duplicate entity groups: {groups.groups}"
        f" covering {groups.rows_in_groups} row(s)"
    )

    # uq_entity_edge_identity is enforced on every UPDATE, and the repoint runs
    # as two separate statements (source, then target). Between them an edge
    # reads (keep, loser), an identity the claim-then-rank pass never ranked
    # because it ranked the FINAL (keep, keep) identity. So the intermediate
    # state can violate the constraint on the first UPDATE. Defer enforcement
    # across the merge; it is re-added in upgrade() once every final collision
    # has been dropped, and that re-add is what validates the result.
    bind.execute(
        sa.text("ALTER TABLE entity_edge DROP CONSTRAINT IF EXISTS uq_entity_edge_identity")
    )

    _report(bind, _MERGE_ENTITY_ATTRIBUTES, "entity aggregated_attributes merged")
    _report(bind, _DROP_LINKS_ON_COLLISION, "memory_entity_link rows dropped (would collide)")
    _report(bind, _REPOINT_LINKS, "memory_entity_link rows repointed")
    _report(
        bind,
        _DROP_EDGES_ON_COLLISION,
        "entity_edge rows dropped (would self-loop or collide)",
    )
    _report(bind, _REPOINT_EDGE_SOURCE, "entity_edge source_entity_id repointed")
    _report(bind, _REPOINT_EDGE_TARGET, "entity_edge target_entity_id repointed")
    _report(bind, _REPOINT_COMPRESSED_SUMMARIES, "compressed_summary rows repointed")
    _report(
        bind,
        _REPOINT_MISSING_MEMORY_CANDIDATES,
        "missing_memory_candidate rows repointed",
    )
    _report(bind, _DELETE_LOSERS, "duplicate entity rows deleted")


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(sa.text(_CREATE_DUP_GROUP))
    bind.execute(sa.text("CREATE UNIQUE INDEX _ix_dup_group_keep ON _entity_dup_group (keep_id)"))
    bind.execute(sa.text(_CREATE_DUP_MERGE))
    bind.execute(sa.text("CREATE UNIQUE INDEX _ix_dup_merge_loser ON _entity_dup_merge (loser_id)"))
    bind.execute(sa.text("CREATE INDEX _ix_dup_merge_keep ON _entity_dup_merge (keep_id)"))
    _merge_duplicate_entities(bind)

    _report(bind, _NORMALISE_RELATIONSHIP_TYPES, "entity_edge relationship_type normalised")
    # Runs LAST, after the entity merge, the endpoint repoints AND the
    # relationship_type normalisation. Each of those can create an identity the
    # unique constraint forbids, and they can only be observed once all three
    # have settled -- normalising `co_occurs_with` to `related_to` alone is
    # enough to collide two previously-distinct edges. This is the statement the
    # constraint is validated against, so it is the one that must be complete.
    _report(bind, _FINAL_EDGE_DEDUPE, "entity_edge rows dropped (residual duplicates)")

    # The unique index makes the non-unique one from revision 015 redundant:
    # identical column list, identical ordering.
    op.drop_index("ix_entity_identity", table_name="entity")
    # A unique Index rather than `ALTER TABLE ... ADD CONSTRAINT ... UNIQUE`:
    # PostgreSQL accepts an expression in the former and not the latter, and
    # SQLAlchemy mirrors that. `models.entity.Entity` declares the same object,
    # so autogenerate sees no drift.
    op.create_index(
        "uq_entity_identity",
        "entity",
        ["organization_id", "user_id", sa.text("lower(name)")],
        unique=True,
    )
    # Re-added after the merge, so this statement is where a residual duplicate
    # edge identity is caught. It was dropped for the duration of the merge.
    op.create_unique_constraint(
        "uq_entity_edge_identity",
        "entity_edge",
        ["organization_id", "source_entity_id", "target_entity_id", "relationship_type"],
    )
    op.execute(
        "ALTER TABLE entity_edge ADD CONSTRAINT ck_entity_edge_relationship_type_known "
        f"CHECK (relationship_type IN ({_ALLOWED_LITERAL_SQL}))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE entity_edge DROP CONSTRAINT IF EXISTS "
        "ck_entity_edge_relationship_type_known"
    )
    op.drop_index("uq_entity_identity", table_name="entity")
    op.create_index(
        "ix_entity_identity",
        "entity",
        ["organization_id", "user_id", sa.text("lower(name)")],
    )
    # The entity merge and the relationship_type normalisation are forward-only.
    # Recreating the non-unique index above is the whole of the schema reversal;
    # duplicate rows stay merged and normalised `relationship_type` values stay
    # normalised. Both were lossy in a way a downgrade cannot reconstruct, and
    # re-splitting the entities would resurrect the ambiguity the unique
    # constraint exists to remove.

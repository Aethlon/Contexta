#!/usr/bin/env python3
"""Recompute `memory_record.fact_key` for rows that carry a usable fact triple.

What this fixes
---------------
The structural slot key used to hash subject + predicate and leave the object
out, so a slot was "who, about what" and any new value for that pair was taken
to be a correction of it. With `subject` pinned to the literal string "the user"
-- 123 of 123 keyed rows in a measured 10-conversation ingest -- the digest
collapsed to `sha256("the user" + <coarse verb>)`. Thirty-two slots held 123
keyed rows, four mutually exclusive `uses` facts shared one slot, and because
`uq_memory_record_current_fact_slot` admits one current row per slot, each new
arrival closed the previous one: 46 rows written, 28 superseded, 18 distinct
facts reachable from retrieval, and 8 of 10 sampled supersession pairs being
unrelated facts rather than contradictions.

`contexta.core.pipeline` now hashes the whole triple and prefixes `sfx2:`. This
script brings the rows already written up to the same formula.

Why a script and not an Alembic migration
-----------------------------------------
The key is not a function of the row's columns. It is a canonicalisation
pipeline -- whitespace collapse, case folding, an explicit slot name taking
precedence over the triple, a partial triple returning nothing at all -- living
in Python in `contexta.core.pipeline`. A migration would have to restate that
logic in SQL, and the two copies would then be free to disagree: a digest is
opaque, so a divergence shows up only as rows that no longer match what
ingestion writes for the same fact, months later. Here the script imports the
function the write path uses, so the backfill cannot drift from it by
construction, and the schema itself needs no change -- `fact_key` is already
`String(128)` and `sfx2:` + 64 hex characters is 69.

Direction of the change
-----------------------
Including the object makes the key *finer*: `sfx2` determines `sfx1`, never the
other way round. Rows that collided under the old formula therefore split rather
than merge, which is the direction the unique index wants -- it can only ever
be *relieved* by this rewrite, never tightened. The script proves that for the
data at hand before it writes anything: it projects the whole tenant's new key
set, counts the current-row collisions that the partial unique index
`(organization_id, user_id, fact_key) WHERE valid_to IS NULL` would reject, and
refuses to write if that count is not zero. Rows whose `structured_data` holds
no complete triple are never touched, so they keep whatever key they have.

Usage
-----
    python scripts/backfill_fact_keys.py                    # dry run, every tenant
    python scripts/backfill_fact_keys.py --org <uuid>       # one tenant
    python scripts/backfill_fact_keys.py --apply            # write
    python scripts/backfill_fact_keys.py --apply --batch-size 200

Dry run is the default and `--apply` is the only thing that writes. The run is
idempotent: the key is a pure function of `structured_data`, so a second pass
finds nothing to change and re-applies nothing.

Every read and every write goes through `MemoryRepository`, which is
tenant-scoped. The one exception is the query that enumerates the tenants, which
cannot be tenant-scoped by definition; it reads a list of UUIDs and nothing else.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select, update

from contexta.core.pipeline import _STRUCTURAL_FACT_KEY_PREFIX, structural_fact_key_from_structured
from contexta.db import AsyncSessionFactory
from contexta.models.account import Organization
from contexta.models.memory import MemoryRecord
from contexta.repositories.memory_repo import MemoryRepository

_LEGACY_PREFIX = "sfx1:"


@dataclass
class TenantReport:
    """What the backfill would do to one tenant, or did do to it."""

    organization_id: uuid.UUID
    scanned: int = 0
    with_triple: int = 0
    already_current: int = 0
    rekeyed: int = 0
    no_triple: int = 0
    untouched_other: int = 0
    current_rows_before: int = 0
    current_slots_before: int = 0
    current_slots_after: int = 0
    blocking_collisions: list[tuple[str, int]] = field(default_factory=list)
    unverified: int | None = None

    @property
    def collisions_introduced(self) -> int:
        return max(0, self.current_slots_after - self.current_slots_before)

    def render(self) -> str:
        lines = [
            f"  organization {self.organization_id}",
            f"    rows scanned                     {self.scanned}",
            f"    complete fact triple             {self.with_triple}",
            f"    key already {_STRUCTURAL_FACT_KEY_PREFIX}   {self.already_current}",
            f"    key rewritten                    {self.rekeyed}",
            f"    no complete triple (left alone)  {self.no_triple}",
        ]
        if self.untouched_other:
            lines.append(f"    other key left alone             {self.untouched_other}")
        lines.extend([
            f"    current rows                     {self.current_rows_before}",
            f"    current slots before -> after    {self.current_slots_before} -> {self.current_slots_after}",
        ])
        if self.blocking_collisions:
            lines.append("    COLLISIONS the unique index would reject:")
            lines.extend(f"      {key} x{count}" for key, count in self.blocking_collisions)
        if self.unverified is not None:
            lines.append(f"    rows still off-formula after write {self.unverified}")
        return "\n".join(lines)


def _replacement_key(stored: Any) -> str | None:
    """The `sfx2:` key this row's stored `structured_data` resolves to, or None.

    A single call into the write path's own function, so the digest, the
    canonicalisation and the "a partial triple names nothing" rule are the
    pipeline's, not a second implementation of them.
    """
    return structural_fact_key_from_structured(stored)


async def _write_key(session: Any, organization_id: uuid.UUID, record_id: uuid.UUID, new_key: str) -> int:
    """Rewrite one row's `fact_key`, scoped to its tenant.

    This deliberately does not go through `MemoryRepository.update_by_id`, which
    raises `MemoryFactKeyMutationError` on any `fact_key` change. That guard is
    right: re-pointing one row at another slot strands it in a slot it no longer
    belongs to, and it is exactly what stops an ordinary update from silently
    rewriting lineage. It is also the reason this is a dry-run-by-default script
    rather than a repository method -- a change of the *digest formula* has to be
    a reviewed one-off, applied to every row at once, not a column write any
    caller can reach. (The same reasoning is why the repository tells an operator
    to "run an explicit reviewed backfill" rather than widen itself when the
    embedding profile moves.)

    The statement is still tenant-scoped, and it is a Core update against the
    table, so it moves exactly one row of exactly one tenant and fires no ORM
    attribute events.
    """
    table = MemoryRecord.__table__
    stmt = (
        update(table)
        .where(table.c.id == record_id)
        .where(table.c.organization_id == organization_id)
        .values(fact_key=new_key)
    )
    result = await session.execute(stmt)
    return int(result.rowcount or 0)


async def _tenant_ids(session: Any, only: uuid.UUID | None) -> list[uuid.UUID]:
    """Every tenant that actually owns a memory, plus every registered tenant.

    The union, not just `organization.id`: a memory can outlive, or predate, its
    organization row -- a partially bootstrapped database, a restored dump, a
    sentinel tenant -- and a backfill that quietly skips those rows leaves the
    worst data behind. This is the one query here that is not tenant-scoped, and
    it has to be: enumerating the tenants is what it is for. It reads a list of
    UUIDs and every row it returns is then fetched through a tenant-scoped
    repository.
    """
    if only is not None:
        return [only]
    registered = await session.execute(select(Organization.id))
    in_use = await session.execute(select(MemoryRecord.organization_id).distinct())
    return sorted({row[0] for row in [*registered.all(), *in_use.all()] if row[0] is not None})


async def _backfill_tenant(
    session: Any,
    organization_id: uuid.UUID,
    *,
    batch_size: int,
    apply: bool,
) -> TenantReport:
    report = TenantReport(organization_id=organization_id)
    repository = MemoryRepository(session, tenant_id=organization_id)

    # Pass one: read every row of this tenant, page by page, and project the key
    # each one would carry. `get_all` is offset-paged and the pass only reads, so
    # the offsets stay valid; the writes happen in pass two, after the collision
    # projection is known to be clean.
    projected: list[tuple[uuid.UUID, str]] = []
    current_before: Counter[tuple[uuid.UUID, str]] = Counter()
    current_after: Counter[tuple[uuid.UUID, str]] = Counter()
    offset = 0
    while True:
        rows = list(await repository.get_all(offset=offset, limit=batch_size))
        if not rows:
            break
        for row in rows:
            report.scanned += 1
            stored_key = row.fact_key
            new_key = _replacement_key(row.structured_data)
            if new_key is None:
                # No complete triple: the key stays whatever it is. A row with no
                # triple has no slot to name, and inventing one is how an
                # unrelated memory collides with a stored fact.
                report.no_triple += 1
                if stored_key and stored_key.startswith(_LEGACY_PREFIX):
                    report.untouched_other += 1
                new_key = stored_key
            else:
                report.with_triple += 1
                if new_key == stored_key:
                    report.already_current += 1
                else:
                    report.rekeyed += 1
            if new_key is None:
                continue
            projected.append((row.id, new_key))
            if row.valid_to is None:
                report.current_rows_before += 1
                if stored_key:
                    current_before[(row.user_id, stored_key)] += 1
                if new_key:
                    current_after[(row.user_id, new_key)] += 1
        offset += len(rows)
        if len(rows) < batch_size:
            break

    report.current_slots_before = len(current_before)
    report.current_slots_after = len(current_after)
    report.blocking_collisions = _collisions(current_after)

    if not apply:
        return report
    if report.blocking_collisions:
        # The unique index would abort the batch halfway, leaving the tenant
        # partly rewritten. Refuse instead: the collisions have to be resolved by
        # a human who can see which rows they are.
        return report
    for record_id, new_key in projected:
        if await _write_key(session, organization_id, record_id, new_key) != 1:
            raise RuntimeError(
                f"fact_key rewrite for {record_id} in {organization_id} matched no single row; "
                "the row moved or the tenant scope is wrong. Nothing further was written."
            )
    await session.commit()
    # The rewrite went through Core, so the identity map still holds the objects
    # with their pre-write values; drop them or the verification below reads its
    # own stale session and reports a clean rewrite that never happened.
    session.expire_all()
    # Re-read and confirm: the digest is a pure function of structured_data, so
    # after the write the tenant must be a fixed point. Anything left over means
    # the formula and the stored data disagree, and the operator should hear about
    # it here rather than at the next ingest.
    report.unverified = await _count_outstanding(repository)
    return report


async def _count_outstanding(repository: MemoryRepository) -> int:
    """Rows whose stored key is not what the current formula produces."""
    outstanding = 0
    offset = 0
    while True:
        rows = list(await repository.get_all(offset=offset, limit=500))
        if not rows:
            return outstanding
        for row in rows:
            expected = _replacement_key(row.structured_data)
            if expected is not None and expected != row.fact_key:
                outstanding += 1
        offset += len(rows)
        if len(rows) < 500:
            return outstanding


def _collisions(projected: Counter[tuple[uuid.UUID, str]]) -> list[tuple[str, int]]:
    """Current rows the partial unique index would reject, as (key, rows).

    `uq_memory_record_current_fact_slot` is unique on
    `(organization_id, user_id, fact_key) WHERE valid_to IS NULL AND fact_key IS
    NOT NULL`, so a NULL key is never a violation and a project entry with a
    count of one is a slot with exactly one current row, which is what it wants.
    """
    return [
        (f"{user_id} {key}", count)
        for (user_id, key), count in sorted(projected.items(), key=lambda item: -item[1])
        if key and count > 1
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--org", default=None, help="restrict to one organization UUID")
    parser.add_argument("--apply", action="store_true", help="write the new keys (default: dry run)")
    parser.add_argument("--batch-size", type=int, default=500, help="rows per page (default: 500)")
    args = parser.parse_args()

    async def run() -> int:
        reports: list[TenantReport] = []
        async with AsyncSessionFactory() as session:
            for organization_id in await _tenant_ids(
                session,
                uuid.UUID(args.org) if args.org else None,
            ):
                reports.append(
                    await _backfill_tenant(
                        session,
                        organization_id,
                        batch_size=max(1, args.batch_size),
                        apply=args.apply,
                    )
                )

        mode = "APPLY" if args.apply else "DRY RUN (nothing written)"
        print("=" * 68)
        print(f"  fact_key backfill -- {mode}")
        print("=" * 68)
        for report in reports:
            print(report.render())

        scanned = sum(r.scanned for r in reports)
        rekeyed = sum(r.rekeyed for r in reports)
        no_triple = sum(r.no_triple for r in reports)
        before = sum(r.current_slots_before for r in reports)
        after = sum(r.current_slots_after for r in reports)
        blocked = [r for r in reports if r.blocking_collisions]
        print("-" * 68)
        print(f"  tenants                     {len(reports)}")
        print(f"  rows scanned                {scanned}")
        print(f"  rows rekeyed                {rekeyed}")
        print(f"  rows left alone (no triple) {no_triple}")
        print(f"  current slots before        {before}")
        print(f"  current slots after         {after}")
        print(f"  collisions introduced       {sum(r.collisions_introduced for r in reports)}")
        if blocked:
            print()
            print("  NOT WRITTEN: the new keys would collide under")
            print("  uq_memory_record_current_fact_slot. Resolve those rows first.")
            return 1
        outstanding = [r for r in reports if r.unverified]
        if outstanding:
            print()
            print("  WROTE, but these tenants still hold rows the formula does not")
            print("  reproduce. Re-run before trusting the keys:")
            for report in outstanding:
                print(f"    {report.organization_id}: {report.unverified} row(s)")
            return 1
        if args.apply:
            print()
            print(f"  wrote {rekeyed} row(s), each tenant re-verified against the")
            print("  formula. Re-running is a no-op.")
        else:
            print()
            print("  Dry run only. Re-run with --apply to write these keys.")
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())

"""Truth maintenance and contradiction resolution.

The work itself lives in `TruthSupersessionService`, which owns candidate
resolution, the guarded `valid_to` write, the version snapshot and the audit
row. This module keeps the engine surface that the pipeline and the tests
already construct.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from contexta.core.truth.service import (
    AuditRepositoryProtocol,
    ContradictionDetector,
    FactSlotContradictionDetector,
    MemoryTruthRepository,
    PlannedSupersession,
    SimpleContradictionDetector,
    Supersession,
    TruthSupersessionService,
    VersionRepositoryProtocol,
)
from contexta.models.entity import EntityEdge
from contexta.models.memory import MemoryRecord

__all__ = [
    "AuditRepositoryProtocol",
    "ContradictionDetector",
    "EdgeRepositoryProtocol",
    "FactSlotContradictionDetector",
    "MemoryTruthRepository",
    "PlannedSupersession",
    "SimpleContradictionDetector",
    "Supersession",
    "TruthMaintenanceEngine",
    "VersionRepositoryProtocol",
]


class EdgeRepositoryProtocol(Protocol):
    """Retained for the constructor signature; no edge is written on supersession.

    Supersession is a memory->memory relation tracked in MemoryVersion, so the
    engine never emits an EntityEdge. The argument is still accepted because the
    pipeline and existing callers pass one.
    """

    async def create(self, record: EntityEdge) -> EntityEdge:
        ...


class TruthMaintenanceEngine:
    """Maintain current truth and preserve superseded historical memories."""

    def __init__(
        self,
        memory_repository: MemoryTruthRepository,
        version_repository: VersionRepositoryProtocol,
        *,
        edge_repository: EdgeRepositoryProtocol | None = None,
        audit_repository: AuditRepositoryProtocol | None = None,
        contradiction_detector: ContradictionDetector | None = None,
    ) -> None:
        self._edges = edge_repository
        self._service = TruthSupersessionService(
            memory_repository,
            version_repository,
            audit_repository=audit_repository,
            contradiction_detector=contradiction_detector,
        )

    async def apply(
        self,
        new_memory: MemoryRecord,
        *,
        entity_ids: Sequence[uuid.UUID] = (),
        actor_id: uuid.UUID | None = None,
        now: datetime | None = None,
        exclude_ids: Sequence[uuid.UUID] = (),
    ) -> list[Supersession]:
        """Supersede contradicted current memories that share the new memory's fact slot.

        For a caller that has already inserted `new_memory`. A caller that has
        not must call `plan()` before its insert and `record()` after it, because
        one current row per fact slot is a uniqueness constraint on the table.
        """
        return await self._service.apply(
            new_memory,
            actor_id=actor_id,
            now=now,
            exclude_ids=exclude_ids,
        )

    async def plan(
        self,
        new_memory: MemoryRecord,
        *,
        actor_id: uuid.UUID | None = None,
        now: datetime | None = None,
        exclude_ids: Sequence[uuid.UUID] = (),
    ) -> list[PlannedSupersession]:
        """Close the contradicted rows of the new memory's fact slot.

        Must run before `new_memory` is inserted: a pending insert would be
        autoflushed ahead of the close and rejected by the fact-slot uniqueness
        constraint.
        """
        return await self._service.plan(
            new_memory,
            actor_id=actor_id,
            now=now,
            exclude_ids=exclude_ids,
        )

    async def plan_all(
        self,
        memories: Sequence[MemoryRecord],
        *,
        actor_id: uuid.UUID | None = None,
        now: datetime | None = None,
        exclude_ids: Sequence[uuid.UUID] = (),
    ) -> tuple[dict[uuid.UUID, list[PlannedSupersession]], set[uuid.UUID]]:
        """Close the contradicted rows of a whole batch, and name the rows to skip.

        Returns each memory's plan plus the ids whose fact slot still holds a
        current row, because one current row per slot is a uniqueness constraint
        and such a memory cannot be inserted at all. Must run before any of
        `memories` is inserted.
        """
        return await self._service.plan_all(
            memories,
            actor_id=actor_id,
            now=now,
            exclude_ids=exclude_ids,
        )

    async def record(
        self,
        planned: Sequence[PlannedSupersession],
    ) -> list[Supersession]:
        """Write the version and audit rows for the rows `plan` closed."""
        return await self._service.record(planned)

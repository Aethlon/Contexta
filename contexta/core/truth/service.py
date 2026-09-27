"""The single owner of memory supersession.

`TruthMaintenanceEngine` used to open-code the whole sequence on every call:
choose a candidate set, decide whether the new memory contradicts it, snapshot
the old row, close its validity window, log the event. Each step was a separate
unguarded write, so two callers -- or a retried ingestion -- could both snapshot
a record that was already superseded, and the candidate set was an arbitrary
window of the user's memories scored with `difflib`. Rephrasing a fact therefore
moved it to a different window, and a same-slot update never closed the old row.

This module owns the sequence instead:

* candidates are resolved by *fact slot* through the ``fact_key`` index, so the
  set is the rows that actually claim to state the same fact, not a text scan;
* the decision compares the values inside one slot, so a rephrasing supersedes
  and a restatement does not;
* the ``valid_to`` write is one conditional ``UPDATE`` guarded by
  ``valid_to IS NULL``. Its row count is the arbiter of who won, so exactly one
  caller can snapshot a record, no matter how many run concurrently;
* the ``MemoryVersion`` snapshot and the ``audit_log`` row are written only by
  that winner.

Why the sequence is split in two
--------------------------------
`uq_memory_record_current_fact_slot` admits one current row per fact slot, so a
replacement cannot be inserted while the incumbent is still current: the close
has to happen *before* the insert. The lineage rows cannot move earlier than
that, because `memory_version.superseded_by_id` references the row being
inserted. A caller that inserts first therefore closes the incumbent after its
own insert, which the index rejects. Hence:

* :meth:`TruthSupersessionService.plan` decides and closes. It must run before
  the replacement row is added to the session, because a pending insert would
  be autoflushed ahead of the close.
* :meth:`TruthSupersessionService.record` writes the snapshot and the audit
  row, and must run after the replacement row is inserted.
* :meth:`TruthSupersessionService.apply` is both, for callers with no insert to
  order around.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Protocol

from contexta.core.types import MemoryType
from contexta.models.audit import AuditLog
from contexta.models.memory import MemoryRecord
from contexta.models.version import MemoryVersion

__all__ = [
    "AuditRepositoryProtocol",
    "ContradictionDetector",
    "FactSlotContradictionDetector",
    "MemoryTruthRepository",
    "PlannedSupersession",
    "SimpleContradictionDetector",
    "Supersession",
    "TruthSupersessionService",
    "VersionRepositoryProtocol",
    "fact_value",
]

# An extractor that names the slot may name the value it asserted alongside it;
# a bare slot name with no value falls back to the memory's own text.
_FACT_VALUE_KEYS = ("fact_value", "value")
_WHITESPACE = re.compile(r"\s+")


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _memory_type_value(memory_type: str | MemoryType) -> str:
    if isinstance(memory_type, MemoryType):
        return memory_type.value
    return str(memory_type)


def _canonical_text(value: object) -> str:
    return _WHITESPACE.sub(" ", str(value or "")).strip().casefold()


def fact_value(memory: object) -> str:
    """The assertion a memory makes, normalised for comparison inside a slot.

    Shared with the deduplication engine: both have to agree on what "the same
    fact, said again" means, or one of them re-stores what the other decided was
    already known.
    """
    structured = getattr(memory, "structured_data", None)
    if isinstance(structured, Mapping):
        for key in _FACT_VALUE_KEYS:
            candidate = structured.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return _canonical_text(candidate)
    return _canonical_text(
        f"{getattr(memory, 'title', '')}\n{getattr(memory, 'content', '')}"
    )


class MemoryTruthRepository(Protocol):
    async def get_current_truths(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[object]:
        ...

    async def supersede(self, old_id: uuid.UUID, valid_to: datetime) -> int:
        ...


class VersionRepositoryProtocol(Protocol):
    async def create(self, record: MemoryVersion) -> MemoryVersion:
        ...


class AuditRepositoryProtocol(Protocol):
    async def create(self, record: AuditLog) -> AuditLog:
        ...


class ContradictionDetector(Protocol):
    async def contradicts(self, new_memory: MemoryRecord, existing_memory: object) -> bool:
        ...


@dataclass(frozen=True)
class Supersession:
    """A completed supersession event."""

    old_memory_id: uuid.UUID
    new_memory_id: uuid.UUID
    valid_to: datetime
    version_id: uuid.UUID | None = None


@dataclass(frozen=True)
class PlannedSupersession:
    """A closed record whose lineage still has to be written.

    Produced by `plan()` and consumed once by `record()`; holding the snapshot
    here is what lets the old row be closed before its replacement is inserted
    while the version still describes the state as it was before the close.
    """

    organization_id: uuid.UUID
    actor_id: uuid.UUID
    new_memory_id: uuid.UUID
    old_memory_id: uuid.UUID
    valid_to: datetime
    old_content: str
    old_structured_data: dict | None
    old_importance: float
    old_valid_from: datetime
    new_content: str
    fact_key: str | None


class FactSlotContradictionDetector:
    """Decide contradiction structurally, from inside one fact slot.

    Candidates arrive already narrowed to the rows sharing the new memory's
    ``fact_key``, so the only question left is whether they assert the same
    thing. Same value is a restatement and leaves the current truth alone; a
    different value closes the older row. Character similarity plays no part,
    which is what kept unrelated rows ("[PERSON_6] attended the standup" against
    "[PERSON_6] attended the postmortem") from closing each other.
    """

    async def contradicts(self, new_memory: MemoryRecord, existing_memory: object) -> bool:
        return fact_value(new_memory) != fact_value(existing_memory)


class SimpleContradictionDetector:
    """Conservative deterministic detector for memories with no fact key.

    Only used for the fallback path, where nothing identifies the slot and the
    candidate set is only narrowed by user and type. It flags a contradiction
    when titles are highly similar and content differs. LLM-based contradiction
    detection can replace this later.
    """

    async def contradicts(self, new_memory: MemoryRecord, existing_memory: object) -> bool:
        title_similarity = SequenceMatcher(
            None,
            new_memory.title.lower(),
            str(getattr(existing_memory, "title", "")).lower(),
        ).ratio()
        return (
            title_similarity >= 0.8
            and new_memory.content.strip()
            != str(getattr(existing_memory, "content", "")).strip()
        )


class TruthSupersessionService:
    """Perform supersession correctly, once, with a full audit trail."""

    def __init__(
        self,
        memory_repository: MemoryTruthRepository,
        version_repository: VersionRepositoryProtocol,
        *,
        audit_repository: AuditRepositoryProtocol | None = None,
        contradiction_detector: ContradictionDetector | None = None,
    ) -> None:
        self._memories = memory_repository
        self._versions = version_repository
        self._audit = audit_repository
        # An explicitly supplied detector (an LLM judge, a test double) speaks
        # for both paths; otherwise the keyed path decides structurally and
        # only the unkeyed fallback falls back to text similarity.
        self._detector = contradiction_detector
        self._slot_detector = FactSlotContradictionDetector()
        self._unkeyed_detector = contradiction_detector or SimpleContradictionDetector()

    async def apply(
        self,
        new_memory: MemoryRecord,
        *,
        actor_id: uuid.UUID | None = None,
        now: datetime | None = None,
        exclude_ids: Sequence[uuid.UUID] = (),
    ) -> list[Supersession]:
        """Decide, close and record in one call.

        Correct for a caller that has already inserted `new_memory`; a caller
        that has not must run `plan()` before its insert and `record()` after it.
        """
        planned = await self.plan(
            new_memory,
            actor_id=actor_id,
            now=now,
            exclude_ids=exclude_ids,
        )
        return await self.record(planned)

    async def plan(
        self,
        new_memory: MemoryRecord,
        *,
        actor_id: uuid.UUID | None = None,
        now: datetime | None = None,
        exclude_ids: Sequence[uuid.UUID] = (),
    ) -> list[PlannedSupersession]:
        """Close every current row of the new memory's fact slot that it contradicts.

        Must run before `new_memory` is inserted, so the slot it takes over is
        already free when the insert is checked.
        """
        timestamp = _naive_utc(now or datetime.now(UTC))
        excluded = {uuid.UUID(str(identifier)) for identifier in exclude_ids}
        detector = self._detector or (
            self._slot_detector
            if getattr(new_memory, "fact_key", None)
            else self._unkeyed_detector
        )
        planned: list[PlannedSupersession] = []

        for existing in await self._candidate_memories(new_memory, excluded):
            if not await detector.contradicts(new_memory, existing):
                continue
            if not await self._close_validity(existing.id, timestamp):
                # Another writer closed this row first; its snapshot is theirs.
                continue
            planned.append(
                PlannedSupersession(
                    organization_id=new_memory.organization_id,
                    actor_id=actor_id or new_memory.user_id,
                    new_memory_id=new_memory.id,
                    old_memory_id=existing.id,
                    valid_to=timestamp,
                    old_content=str(getattr(existing, "content", "") or ""),
                    old_structured_data=getattr(existing, "structured_data", None),
                    old_importance=float(getattr(existing, "importance", 0.0) or 0.0),
                    old_valid_from=_naive_utc(getattr(existing, "valid_from", None) or timestamp),
                    new_content=new_memory.content,
                    fact_key=getattr(new_memory, "fact_key", None),
                )
            )
        return planned

    async def record(self, planned: Sequence[PlannedSupersession]) -> list[Supersession]:
        """Write the version and audit rows for closed records.

        Must run after the replacement row is inserted:
        `memory_version.superseded_by_id` references it. Consume each plan once;
        replaying one would write a second version of the same history.
        """
        recorded: list[Supersession] = []
        for item in planned:
            version = await self._versions.create(
                MemoryVersion(
                    memory_id=item.old_memory_id,
                    superseded_by_id=item.new_memory_id,
                    content=item.old_content,
                    structured_data=item.old_structured_data,
                    importance=item.old_importance,
                    valid_from=item.old_valid_from,
                    valid_to=item.valid_to,
                )
            )
            await self._log_supersession(item, version.id)
            recorded.append(
                Supersession(
                    old_memory_id=item.old_memory_id,
                    new_memory_id=item.new_memory_id,
                    valid_to=item.valid_to,
                    version_id=version.id,
                )
            )
        return recorded

    async def _candidate_memories(
        self,
        new_memory: MemoryRecord,
        excluded: set[uuid.UUID],
    ) -> list[object]:
        """Rows that claim the same fact as `new_memory`, newest first."""
        fact_key = getattr(new_memory, "fact_key", None)
        if fact_key and hasattr(self._memories, "get_current_by_fact_key"):
            candidates = await self._memories.get_current_by_fact_key(  # type: ignore[attr-defined]
                fact_key,
                user_id=new_memory.user_id,
                memory_type=_memory_type_value(new_memory.memory_type),
            )
        elif hasattr(self._memories, "get_by_type"):
            candidates = await self._memories.get_by_type(  # type: ignore[attr-defined]
                new_memory.user_id,
                new_memory.memory_type,
            )
        else:
            candidates = await self._memories.get_current_truths(new_memory.user_id)
        return [
            memory
            for memory in candidates
            if memory.id != new_memory.id
            and memory.id not in excluded
            and getattr(memory, "valid_to", None) is None
            and _memory_type_value(getattr(memory, "memory_type", ""))
            == _memory_type_value(new_memory.memory_type)
        ]

    async def _close_validity(self, record_id: uuid.UUID, valid_to: datetime) -> int:
        """Close one row if it is still current; 0 means someone else won."""
        claim = getattr(self._memories, "supersede_if_current", None)
        if claim is not None:
            return await claim(record_id, valid_to)
        return await self._memories.supersede(record_id, valid_to)

    async def _log_supersession(
        self,
        item: PlannedSupersession,
        version_id: uuid.UUID,
    ) -> None:
        # Lineage is a memory->memory relation recorded in
        # MemoryVersion.superseded_by_id. EntityEdge only links entities, so the
        # entity->same-entity SUPERSEDED_BY self-loops this used to emit only
        # polluted graph traversal; the version and audit rows carry the lineage.
        if self._audit is None:
            return
        await self._audit.create(
            AuditLog(
                organization_id=item.organization_id,
                actor_id=item.actor_id,
                operation_type="memory_superseded",
                target_id=item.old_memory_id,
                details={
                    "old_memory_id": str(item.old_memory_id),
                    "new_memory_id": str(item.new_memory_id),
                    "old_content": item.old_content,
                    "new_content": item.new_content,
                    "fact_key": item.fact_key,
                    "version_id": str(version_id),
                },
            )
        )

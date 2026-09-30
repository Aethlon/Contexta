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
* the decision compares the values inside one slot, and closes a row only when
  the two values are comparable corrections of the same attribute -- two amounts,
  two dates, two codes -- so a restatement does nothing and an unrelated value
  does nothing;
* the extractor's own ``status`` is honoured: a claim the model marked
  ``superseded`` never becomes the current truth of a slot;
* the ``valid_to`` write is one conditional ``UPDATE`` guarded by
  ``valid_to IS NULL``. Its row count is the arbiter of who won, so exactly one
  caller can snapshot a record, no matter how many run concurrently;
* the ``MemoryVersion`` snapshot and the ``audit_log`` row are written only by
  that winner.

Why supersession is narrower than it was
---------------------------------------
This service used to close a slot on any difference of the values inside it,
which was safe when a slot was subject+predicate and every row in one was
therefore a second reading of the same attribute. It is not safe once a slot is
the whole triple: measured over a 10-conversation ingest, 28 of 46 stored rows
were closed, 8 of the 10 sampled pairs were unrelated, and the closed rows were
unreachable from every retrieval channel afterwards. The rules below close a row
only when the evidence says which of the two claims wins, and `plan_all` hands
back the rows that consequently must not be inserted at all rather than letting
the uniqueness constraint abort the observation.

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
from contexta.models.memory import MemoryContentDecryptionError, MemoryRecord
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
    "extraction_status",
    "fact_value",
    "refuses_to_close",
]

# An extractor that names the slot may name the value it asserted alongside it;
# a bare slot name with no value falls back to the memory's own text.
_FACT_VALUE_KEYS = ("fact_value", "value")
_WHITESPACE = re.compile(r"\s+")

# The statuses of `contexta.contracts.extraction.STATUSES` that carry an
# ordering claim, and the one that carries "this is the standing truth".
_STATUS_CURRENT = "current"
_STATUS_SUPERSEDED = "superseded"
_STATUS_TEMPORARY = "temporary"

# ── value comparability ────────────────────────────────────────────────
# Inside one fact slot, "these two values differ" is not the same claim as "one
# of them corrects the other". That distinction used to be free, because a slot
# was subject+predicate and any two rows in it were by construction two readings
# of one attribute. With the object in the slot digest a slot is the whole
# assertion, so the values inside one are usually equal by construction and the
# only ones that can still differ are the two the extractor put there on purpose.
# A difference is therefore treated as a correction only when both sides
# normalise to the same kind of value.
_KIND_CURRENCY = "currency"
_KIND_DATE = "date"
_KIND_NUMBER = "number"
_KIND_IDENTIFIER = "identifier"
_KIND_TEXT = "text"
_KIND_EMPTY = "empty"

# `number` and `currency` answer the same question -- how much -- so a bare
# "45000" and a "$45,000" are two spellings of one value, not two attributes.
_NUMERIC_KINDS = frozenset({_KIND_CURRENCY, _KIND_NUMBER})

_CURRENCY_CODES = frozenset(
    {
        "aed", "ars", "aud", "brl", "cad", "chf", "clp", "cny", "cop", "czk",
        "dkk", "eur", "gbp", "hkd", "idr", "ils", "inr", "jpy", "krw", "mxn",
        "myr", "ngn", "nok", "nzd", "pen", "php", "pln", "rub", "sar", "sek",
        "sgd", "thb", "try", "twd", "uah", "usd", "vnd", "zar",
    }
)
_CURRENCY_SYMBOLS = "$€£¥₹₽₩₪฿₺₫₴₦₱"
_CURRENCY_SYMBOL_RE = re.compile(f"[{re.escape(_CURRENCY_SYMBOLS)}]")
_CURRENCY_CODE_RE = re.compile(r"\b[a-z]{3}\b")

# A bare year, an ISO-8601 date (with optional time and offset), and the
# slashed form people write. Deliberately narrow: an unrecognised date shape
# falls through to text, which is the conservative kind.
_YEAR_RE = re.compile(r"(?:1\d{3}|2\d{3})")
_ISO_DATE_RE = re.compile(
    r"\d{4}-\d{1,2}-\d{1,2}"
    r"(?:[t ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:z|[+-]\d{2}:?\d{2})?)?"
)
_SLASHED_DATE_RE = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}")
_DATE_RES = (_YEAR_RE, _ISO_DATE_RE, _SLASHED_DATE_RE)

# A number, with or without thousands separators and spacing. `_` is a digit
# separator in some locales and an identifier character in others; it is only
# removed inside a candidate that is otherwise all digits, so `function_15`
# cannot become `15`.
_PLAIN_NUMBER_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")
_GROUPING_RE = re.compile(r"[,\s_]")

# A short code-like token: no spaces, and the punctuation that shows up in
# version numbers, regions, package names and handles.
_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._+#@/-]*$")

# Below this many words a free-text value is short enough that a difference
# against a long phrase is a change of subject rather than a reworded value.
_SHORT_TEXT_WORDS = 3


@dataclass(frozen=True)
class _ValueShape:
    """What one asserted value looks like once normalised for comparison."""

    kind: str
    number: float | None = None


def _as_number(text: str) -> float | None:
    """Parse `text` as a single number, or None when it is not one."""
    cleaned = _GROUPING_RE.sub("", text)
    if not _PLAIN_NUMBER_RE.fullmatch(cleaned):
        return None
    return float(cleaned)


def _currency_amount(text: str) -> float | None:
    """Parse the amount in a money literal, or None when there is not one.

    "EUR 1,200", "$45,000" and "45000eur" all carry a currency marker; a bare
    "45000" does not, so it stays a plain number rather than a currency whose
    code happened to be lost.
    """
    has_symbol = _CURRENCY_SYMBOL_RE.search(text) is not None
    has_code = any(
        token in _CURRENCY_CODES for token in _CURRENCY_CODE_RE.findall(text)
    )
    if not has_symbol and not has_code:
        return None
    remainder = _CURRENCY_SYMBOL_RE.sub(" ", text)
    for token in _CURRENCY_CODE_RE.findall(remainder):
        remainder = remainder.replace(token, " ")
    return _as_number(remainder)


def _value_shape(value: str) -> _ValueShape:
    """Classify one asserted value. Deterministic, and total on any input."""
    text = _canonical_text(value)
    if not text:
        return _ValueShape(_KIND_EMPTY)
    if any(pattern.fullmatch(text) for pattern in _DATE_RES):
        return _ValueShape(_KIND_DATE)
    amount = _currency_amount(text)
    if amount is not None:
        return _ValueShape(_KIND_CURRENCY, amount)
    number = _as_number(text)
    if number is not None:
        return _ValueShape(_KIND_NUMBER, number)
    if _IDENTIFIER_RE.match(text):
        return _ValueShape(_KIND_IDENTIFIER)
    return _ValueShape(_KIND_TEXT)


def _is_short_text(value: str) -> bool:
    return 0 < len(value.split()) <= _SHORT_TEXT_WORDS


def _values_comparable(a: str, b: str) -> bool:
    """Whether a difference between two values is a correction of one attribute.

    True only when both sides are the same kind of value:

    * two money amounts, or two plain numbers, or a number and an amount -- all
      amount-like, so `45000` against `93000` is a correction of one number;
    * two dates, ISO or years;
    * two short code-like tokens, e.g. two version strings or two regions;
    * two free-text phrases of comparable length.

    False when the kinds differ -- a number against a bare identifier, a long
    phrase against a short one -- because a difference between two different
    kinds of value says nothing about which is the correction, and False when
    either side is empty, because there is no value to compare.

    The failure mode this avoids is measured, not hypothetical: a credential row
    closed by a code snippet, `the user uses multiplication` closed by
    `the user uses function_15`.
    """
    left, right = _value_shape(a), _value_shape(b)
    if _KIND_EMPTY in (left.kind, right.kind):
        return False
    if left.kind in _NUMERIC_KINDS and right.kind in _NUMERIC_KINDS:
        return True
    if left.kind != right.kind:
        return False
    return not (left.kind == _KIND_TEXT and _is_short_text(a) != _is_short_text(b))


def _values_equivalent(a: str, b: str) -> bool:
    """Whether two differently spelled values assert the same amount.

    Only the numeric kinds carry a value that survives reformatting: "45000" and
    "$45,000" are one number written twice, and treating the second as a
    correction would supersede a row in favour of itself.
    """
    left, right = _value_shape(a), _value_shape(b)
    if left.number is None or right.number is None:
        return False
    return left.number == right.number


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


def _readable_content(memory: object) -> str:
    """The memory's content as text, decrypting it when the column is ciphertext.

    `MemoryRepository.create` writes `memory_record.content` as
    `enc:v1:<aes-gcm>`, and the nonce is random, so two rows holding
    byte-identical plaintext never compare equal in that column. Reading the
    attribute the model exposes for exactly this purpose is the only way to
    compare what the memory says rather than how it was sealed. For an
    unencrypted row it returns the column unchanged, so both storage paths
    answer identically.

    A decryption failure degrades to the empty string rather than raising:
    supersession is a deletion, and "cannot read it" is not a reason to delete
    anything. Any other failure is a real fault and is left to propagate.
    """
    try:
        plaintext = getattr(memory, "plaintext_content", None)
    except MemoryContentDecryptionError:
        return ""
    if isinstance(plaintext, str):
        return plaintext
    return str(getattr(memory, "content", "") or "")


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
    return _canonical_text(f"{getattr(memory, 'title', '')}\n{_readable_content(memory)}")


def extraction_status(memory: object) -> str:
    """The status the extraction contract gave this claim, or "".

    `contexta.contracts.extraction.STATUSES` is part of the response schema, and
    the prompt tells the model to label the earlier claim "superseded" when the
    user corrects themselves. The extractor has therefore been answering the
    question supersession exists to ask, and the answer landed in
    `structured_data.status` where nothing read it. Measured over one ingest: in
    16 of 51 supersessions the engine closed a `status: current` row in favour of
    a row the model had explicitly labelled `superseded`, some of them with a
    backwards `valid_from`.

    The nested `fact.status` is accepted too, because the fine-tuned extractor
    emits the claim fields as bare siblings of `structured_data` and the triple
    is the only part that gets nested under `fact`.
    """
    structured = getattr(memory, "structured_data", None)
    if not isinstance(structured, Mapping):
        return ""
    for source in (structured, structured.get("fact")):
        if not isinstance(source, Mapping):
            continue
        status = source.get("status")
        if isinstance(status, str) and status.strip():
            return _canonical_text(status)
    return ""


def _strictly_after(later: datetime | None, earlier: datetime | None) -> bool:
    if later is None or earlier is None:
        return False
    return _naive_utc(later) > _naive_utc(earlier)


def refuses_to_close(
    candidate_status: str,
    incumbent_status: str,
    candidate_valid_from: datetime | None,
    incumbent_valid_from: datetime | None,
) -> bool:
    """Whether a candidate must not close the incumbent it was matched against.

    Ordered from the extractor's own statement of intent to the weakest signal:

    * A candidate the model marked `superseded` never retires a `current` row.
      The one case where it may is a candidate that is itself strictly newer than
      the row it would replace, where the two are a correction and a
      re-withdrawal rather than an out-of-order arrival.
    * A `temporary` claim -- a visit, a stint, a "while I was there" -- does not
      close a `current` row either. Publishing a temporary state as the standing
      one is how a past tense becomes the present.
    * Otherwise a candidate that starts strictly *before* the incumbent is
      refused. A row dated earlier than the truth it would replace is a late
      arrival, not a correction of it, and closing the incumbent would move the
      present backwards.
    """
    if candidate_status == _STATUS_SUPERSEDED:
        if incumbent_status != _STATUS_CURRENT:
            return False
        return not _strictly_after(candidate_valid_from, incumbent_valid_from)
    if candidate_status == _STATUS_TEMPORARY and incumbent_status == _STATUS_CURRENT:
        return True
    if candidate_valid_from is not None and incumbent_valid_from is not None:
        return _naive_utc(candidate_valid_from) < _naive_utc(incumbent_valid_from)
    return False


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
    thing. The bar for closing one is therefore high, and deliberately so.

    A slot is the whole assertion -- subject, predicate, context and object -- so
    two rows in one slot normally assert the same value by construction, and the
    ones that differ are the ones an extractor put there on purpose. Three ways
    to differ, three answers:

    * the same value spelled differently, including a reformatting that survives
      normalisation ("45000" and "$45,000") -- a restatement, so nothing is
      closed;
    * a different value of the same kind, e.g. two amounts, two dates, two
      version strings -- a correction, so the older row is closed;
    * a different *kind* of value, e.g. an amount against an identifier, or a
      long phrase against a short one -- not a correction of anything, so
      nothing is closed. These were 8 of the 10 supersessions sampled from a
      10-conversation ingest; closing a credential row because a code snippet
      arrived afterwards is data loss dressed as truth maintenance.

    Character similarity plays no part. A slot lookup already did the narrowing,
    and a title ratio could only add ways to close the wrong row.
    """

    async def contradicts(self, new_memory: MemoryRecord, existing_memory: object) -> bool:
        new_value = fact_value(new_memory)
        existing_value = fact_value(existing_memory)
        if new_value == existing_value:
            return False
        if _values_equivalent(new_value, existing_value):
            return False
        return _values_comparable(new_value, existing_value)


class SimpleContradictionDetector:
    """Conservative deterministic detector for memories with no fact key.

    Only used for the fallback path, where nothing identifies the slot and the
    candidate set is only narrowed by user and type. It needs the same two
    things that path can offer: a title that is recognisably the same headline,
    and a value that genuinely differs. Both are read as text -- `content` is
    AES-GCM ciphertext on a stored row and the nonce is random, so comparing the
    column made the "content differs" half of this condition permanently true
    and the detector degenerated to a bare title ratio, which fired on any two
    memories that shared a headline. LLM-based contradiction detection can
    replace this later.
    """

    _TITLE_SIMILARITY = 0.8

    async def contradicts(self, new_memory: MemoryRecord, existing_memory: object) -> bool:
        new_title = _canonical_text(getattr(new_memory, "title", ""))
        existing_title = _canonical_text(getattr(existing_memory, "title", ""))
        if not new_title or not existing_title:
            return False
        if SequenceMatcher(None, new_title, existing_title).ratio() < self._TITLE_SIMILARITY:
            return False
        new_value = fact_value(new_memory)
        existing_value = fact_value(existing_memory)
        if not new_value or not existing_value:
            return False
        if new_value == existing_value:
            return False
        if _values_equivalent(new_value, existing_value):
            return False
        return _values_comparable(new_value, existing_value)


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
        already free when the insert is checked. For a batch, use `plan_all`,
        which also reports the rows that must not be inserted at all.
        """
        planned, _ = await self.plan_all(
            [new_memory],
            actor_id=actor_id,
            now=now,
            exclude_ids=exclude_ids,
        )
        return planned.get(new_memory.id, [])

    async def plan_all(
        self,
        memories: Sequence[MemoryRecord],
        *,
        actor_id: uuid.UUID | None = None,
        now: datetime | None = None,
        exclude_ids: Sequence[uuid.UUID] = (),
    ) -> tuple[dict[uuid.UUID, list[PlannedSupersession]], set[uuid.UUID]]:
        """Plan a whole batch, and name the rows that must not be inserted.

        Returns the per-memory plans plus the set of memory ids whose fact slot
        still holds a current row afterwards: a candidate the detector refused to
        close, or one another writer closed first. Such a row cannot be
        inserted -- `uq_memory_record_current_fact_slot` rejects it -- and that
        rejection aborts the whole observation rather than the one memory, so a
        caller inserting a batch has to drop these and report them. It is the
        price of a supersession rule that declines to guess: keeping a fact we
        cannot place, and losing the duplicate, is the recoverable direction.

        Must run before any of `memories` is inserted.
        """
        timestamp = _naive_utc(now or datetime.now(UTC))
        excluded = {uuid.UUID(str(identifier)) for identifier in exclude_ids}
        planned_by_memory: dict[uuid.UUID, list[PlannedSupersession]] = {}
        blocked: set[uuid.UUID] = set()

        for new_memory in memories:
            planned_by_memory[new_memory.id] = await self._plan_one(
                new_memory,
                timestamp=timestamp,
                actor_id=actor_id,
                excluded=excluded,
                is_blocked=blocked,
            )
        return planned_by_memory, blocked

    async def _plan_one(
        self,
        new_memory: MemoryRecord,
        *,
        timestamp: datetime,
        actor_id: uuid.UUID | None,
        excluded: set[uuid.UUID],
        is_blocked: set[uuid.UUID],
    ) -> list[PlannedSupersession]:
        planned: list[PlannedSupersession] = []
        candidate_status = extraction_status(new_memory)
        if candidate_status == _STATUS_SUPERSEDED:
            # The model already said which of the two claims is the standing one.
            # Honouring that is the whole point of the status field, and skipping
            # the row outright is the conservative reading: a claim labelled
            # superseded can never become the current truth of a slot, whatever
            # its timestamp says. `refuses_to_close` carries the same rule in
            # ordered form; this is the early exit that makes it unconditional.
            if await self._candidate_memories(new_memory, excluded):
                # Still report the slot: the row is not stored, and it could not
                # have been, so the batch has to know not to insert it.
                is_blocked.add(new_memory.id)
            return planned

        candidate_valid_from = getattr(new_memory, "valid_from", None)
        detector = self._detector or (
            self._slot_detector
            if getattr(new_memory, "fact_key", None)
            else self._unkeyed_detector
        )
        candidates = await self._candidate_memories(new_memory, excluded)

        for existing in candidates:
            if not await detector.contradicts(new_memory, existing):
                continue
            if refuses_to_close(
                candidate_status,
                extraction_status(existing),
                candidate_valid_from,
                getattr(existing, "valid_from", None),
            ):
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

        # One current row per slot is a uniqueness constraint, so a slot we did
        # not clear is a slot the new row cannot enter.
        if candidates and len(planned) < len(candidates):
            is_blocked.add(new_memory.id)
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

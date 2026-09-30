"""Slot semantics after `object` entered the structural fact-key digest.

The damage these tests pin down, measured over a 10-conversation ingest: 46 rows
written, 28 superseded, 18 distinct facts reachable from active retrieval, 32
slots for 123 keyed rows, `subject` the literal string "the user" in all 123.
Zero of ten sampled supersession pairs were real contradictions and eight were
unrelated, because the digest was `sha256("the user" + <coarse verb>)`: four
mutually exclusive `uses` facts shared one slot, and one current row per slot
meant each new arrival closed the previous one.

So the digest covers the object, and the decisions that used to be implicit in a
key collision moved into two explicit places: a value-comparability gate, and the
extractor's own `status`. The last test measures the ratio directly, because
that ratio is the number that was wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from contexta.core.pipeline import fact_key_for_memory
from contexta.core.schemas import ExtractedMemory
from contexta.core.truth.maintenance import TruthMaintenanceEngine
from contexta.core.truth.service import (
    FactSlotContradictionDetector,
    SimpleContradictionDetector,
    _values_comparable,
    refuses_to_close,
)
from contexta.core.types import MemoryType, SourceType
from contexta.models.memory import MemoryRecord

_LEGACY_KEY = re.compile(r"^[0-9a-f]{64}$")


def extracted(
    *,
    subject: str,
    predicate: str,
    obj: str,
    context: str | None = None,
    status: str = "current",
    memory_type: MemoryType = MemoryType.FACT,
) -> ExtractedMemory:
    """An extraction shaped like the fine-tuned extractor's real output."""
    fact: dict[str, str] = {"subject": subject, "predicate": predicate, "object": obj}
    if context is not None:
        fact["context"] = context
    return ExtractedMemory(
        memory_type=memory_type,
        source_type=SourceType.USER_EXPLICIT,
        title=f"{predicate} {obj}",
        content=f"The user {predicate.replace('_', ' ')} {obj}.",
        structured_data={"fact": fact, "fact_value": obj, "status": status},
    )


def key_of(memory: ExtractedMemory) -> str:
    return fact_key_for_memory(memory, uuid4(), uuid4())


# --- the object is part of the slot ---------------------------------------


def test_two_objects_of_one_attribute_produce_different_keys() -> None:
    """The failure this whole change exists to stop.

    `the user uses multiplication` and `the user uses function_15` are not two
    readings of one fact. Under the old digest they hashed to one slot, the
    second arrival closed the first, and both facts then came back through
    retrieval as a single row.
    """
    multiplication = key_of(extracted(subject="the user", predicate="uses", obj="multiplication"))
    function = key_of(extracted(subject="the user", predicate="uses", obj="function_15"))

    assert multiplication != function


def test_four_mutually_exclusive_facts_keep_four_slots() -> None:
    keys = {
        key_of(extracted(subject="the user", predicate="uses", obj=obj))
        for obj in ("multiplication", "function_15", "the command line", "spreadsheets")
    }

    assert len(keys) == 4


def test_identical_triple_with_different_spacing_and_case_is_one_key() -> None:
    first = key_of(extracted(subject="Fatima Okafor", predicate="lives_in", obj="Lisbon"))
    second = key_of(extracted(subject="  fatima   OKAFOR ", predicate="LIVES_IN", obj="lisbon"))

    assert first == second


def test_context_still_scopes_a_slot() -> None:
    plain = key_of(extracted(subject="Atlas", predicate="version", obj="2.1"))
    staged = key_of(extracted(subject="Atlas", predicate="version", obj="2.1", context="staging"))

    assert plain != staged


# --- a partial triple names no slot at all --------------------------------


@pytest.mark.parametrize(
    "fact",
    [
        {"subject": "the user", "predicate": "uses"},
        {"subject": "the user", "object": "multiplication"},
        {"predicate": "uses", "object": "multiplication"},
        {"subject": "   ", "predicate": "uses", "object": "multiplication"},
        {"subject": "the user", "predicate": "", "object": "multiplication"},
        {"subject": "the user", "predicate": "uses", "object": "  "},
        {"subject": ["the user"], "predicate": "uses", "object": "multiplication"},
    ],
)
def test_a_partial_triple_falls_back_instead_of_guessing(fact: dict[str, Any]) -> None:
    memory = ExtractedMemory(
        memory_type=MemoryType.FACT,
        source_type=SourceType.USER_EXPLICIT,
        title="Fact",
        content="Something worth remembering.",
        structured_data={"fact": fact},
    )

    key = key_of(memory)

    assert _LEGACY_KEY.match(key)


def test_new_keys_are_prefixed_and_never_look_like_a_legacy_hash() -> None:
    structural = key_of(extracted(subject="the user", predicate="uses", obj="multiplication"))
    legacy = key_of(
        ExtractedMemory(
            memory_type=MemoryType.FACT,
            source_type=SourceType.USER_EXPLICIT,
            title="No triple",
            content="Nothing structured here.",
        )
    )

    assert structural.startswith("sfx2:")
    assert len(structural) == len("sfx2:") + 64
    assert not _LEGACY_KEY.match(structural)
    assert _LEGACY_KEY.match(legacy)
    # Different prefix, and the digest is over a different formula, so no
    # pre-existing sfx1 key can alias onto an sfx2 slot or the reverse.
    assert not structural.startswith("sfx1:")


# --- the comparability gate ------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("$45,000", "$93,000"),
        ("$45,000", "45000 EUR"),
        ("EUR 1,200", "1.200"),
        ("45000", "93000"),
        ("$1,200.50", "$1,200.75"),
        ("2024-03-01", "2025-11-30T08:15:00Z"),
        ("2024", "1999"),
        ("03/01/2024", "12/31/2025"),
        ("2.1.0", "2.1.1"),
        ("eu-west-1", "us-east-1"),
    ],
)
def test_two_values_of_the_same_kind_are_comparable(left: str, right: str) -> None:
    assert _values_comparable(left, right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        # An amount is not a correction of a code.
        ("45000", "function_15"),
        ("$45,000", "eu-west-1"),
        # A long phrase is not a correction of a short one.
        ("the user uses multiplication", "function_15"),
        ("lives in lisbon, portugal and works remotely", "lisbon"),
        # Neither side is a value at all.
        ("", "45000"),
        ("45000", ""),
        ("", ""),
        ("   ", "45000"),
    ],
)
def test_two_values_of_different_kinds_are_not_comparable(left: str, right: str) -> None:
    assert not _values_comparable(left, right)


def test_numeric_comparison_is_value_based_not_string_identical() -> None:
    # "45000" and "93000" are two readings of one number, so the second is a
    # correction of the first rather than an unrelated value. The detector, not
    # this predicate, is what notices that a *reformatting* is not a correction.
    assert _values_comparable("45000", "93000")
    assert _values_comparable("45000", "45000")


async def test_a_reformatted_amount_does_not_close_a_slot() -> None:
    organization_id, user_id = uuid4(), uuid4()
    slot = "the user|salary"
    old = record_for(
        organization_id, user_id, slot, value="$45,000", content="The salary is $45,000."
    )
    new = record_for(organization_id, user_id, slot, value="45000", content="The salary is 45000.")

    assert not await FactSlotContradictionDetector().contradicts(new, old)


async def test_a_genuine_correction_of_a_comparable_value_closes() -> None:
    organization_id, user_id = uuid4(), uuid4()
    slot = "the user|salary"
    old = record_for(organization_id, user_id, slot, value="$45,000", content="The salary is $45,000.")
    new = record_for(organization_id, user_id, slot, value="$93,000", content="The salary is $93,000.")

    assert await FactSlotContradictionDetector().contradicts(new, old)


# --- the extractor's own status is honoured --------------------------------


@dataclass
class SlotRepository:
    rows: list[MemoryRecord]
    closed: list[tuple[UUID, datetime]] = field(default_factory=list)

    async def get_current_by_fact_key(
        self,
        fact_key: str,
        *,
        user_id: UUID | None = None,
        memory_type: str | None = None,
        **_: Any,
    ) -> list[MemoryRecord]:
        return [
            row
            for row in self.rows
            if row.fact_key == fact_key
            and row.valid_to is None
            and (user_id is None or row.user_id == user_id)
            and (memory_type is None or row.memory_type == memory_type)
        ]

    async def supersede_if_current(self, record_id: UUID, valid_to: datetime) -> int:
        for row in self.rows:
            if row.id == record_id and row.valid_to is None:
                row.valid_to = valid_to
                self.closed.append((record_id, valid_to))
                return 1
        return 0


@dataclass
class Collects:
    records: list[Any] = field(default_factory=list)

    async def create(self, record: Any) -> Any:
        self.records.append(record)
        return record


def record_for(
    organization_id: UUID,
    user_id: UUID,
    fact_key: str,
    *,
    value: str,
    content: str,
    status: str = "current",
    valid_from: datetime | None = None,
    title: str = "The user's salary",
) -> MemoryRecord:
    now = datetime.now(UTC).replace(tzinfo=None)
    return MemoryRecord(
        id=uuid4(),
        user_id=user_id,
        organization_id=organization_id,
        memory_type=MemoryType.FACT.value,
        title=title,
        content=content,
        source_type=SourceType.USER_EXPLICIT.value,
        structured_data={"fact_key": fact_key, "fact_value": value, "status": status},
        confidence=1.0,
        importance=0.5,
        fact_key=fact_key,
        valid_from=valid_from or now,
        valid_to=None,
    )


async def plan_for(
    incumbent: MemoryRecord,
    candidate: MemoryRecord,
) -> tuple[SlotRepository, list[Any]]:
    repository = SlotRepository(rows=[incumbent])
    versions = Collects()
    engine = TruthMaintenanceEngine(repository, versions)
    planned = await engine.plan(candidate, actor_id=incumbent.user_id)
    return repository, planned


async def test_a_superseded_candidate_never_wins() -> None:
    organization_id, user_id = uuid4(), uuid4()
    slot = "the user|salary"
    now = datetime.now(UTC).replace(tzinfo=None)
    incumbent = record_for(
        organization_id, user_id, slot, value="$45,000", content="The salary is $45,000."
    )
    # The model already told us this claim is the earlier one, and it arrives
    # later than the truth it would otherwise retire.
    candidate = record_for(
        organization_id,
        user_id,
        slot,
        value="$93,000",
        content="The salary is $93,000.",
        status="superseded",
        valid_from=now + timedelta(minutes=5),
    )

    repository, planned = await plan_for(incumbent, candidate)

    assert planned == []
    assert repository.closed == []
    assert incumbent.valid_to is None


async def test_a_current_incumbent_survives_a_superseded_candidate_with_an_earlier_valid_from() -> None:
    organization_id, user_id = uuid4(), uuid4()
    slot = "the user|salary"
    now = datetime.now(UTC).replace(tzinfo=None)
    incumbent = record_for(
        organization_id,
        user_id,
        slot,
        value="$45,000",
        content="The salary is $45,000.",
        valid_from=now,
    )
    candidate = record_for(
        organization_id,
        user_id,
        slot,
        value="$93,000",
        content="The salary is $93,000.",
        status="superseded",
        valid_from=now - timedelta(days=1),
    )

    repository, planned = await plan_for(incumbent, candidate)

    assert planned == []
    assert repository.closed == []
    assert refuses_to_close("superseded", "current", candidate.valid_from, incumbent.valid_from)


async def test_a_temporary_candidate_does_not_close_a_current_row() -> None:
    organization_id, user_id = uuid4(), uuid4()
    slot = "the user|employer"
    incumbent = record_for(
        organization_id,
        user_id,
        slot,
        value="Contoso",
        content="The user works at Contoso.",
        title="Employer",
    )
    candidate = record_for(
        organization_id,
        user_id,
        slot,
        value="Fabrikam",
        content="The user worked at Fabrikam last summer.",
        status="temporary",
        title="Employer",
    )

    repository, planned = await plan_for(incumbent, candidate)

    assert planned == []
    assert repository.closed == []
    assert incumbent.valid_to is None


async def test_a_correction_within_a_named_slot_still_supersedes() -> None:
    """The close must not become unreachable, or truth maintenance is dead code."""
    organization_id, user_id = uuid4(), uuid4()
    slot = "the user|salary"
    incumbent = record_for(
        organization_id, user_id, slot, value="$45,000", content="The salary is $45,000."
    )
    candidate = record_for(
        organization_id, user_id, slot, value="$93,000", content="The salary is $93,000."
    )

    repository, planned = await plan_for(incumbent, candidate)

    assert len(planned) == 1
    assert planned[0].old_memory_id == incumbent.id
    assert repository.closed == [(incumbent.id, planned[0].valid_to)]


async def test_plan_all_reports_a_row_whose_slot_it_declined_to_clear() -> None:
    """One current row per slot is a uniqueness constraint.

    A slot the engine refuses to clear is a slot the new row cannot enter, and
    inserting it anyway aborts the whole observation. `plan_all` names those rows
    so the batch can drop them instead.
    """
    organization_id, user_id = uuid4(), uuid4()
    slot = "the user|salary"
    incumbent = record_for(
        organization_id, user_id, slot, value="$45,000", content="The salary is $45,000."
    )
    candidate = record_for(
        organization_id,
        user_id,
        slot,
        value="$93,000",
        content="The salary is $93,000.",
        status="superseded",
    )
    engine = TruthMaintenanceEngine(SlotRepository(rows=[incumbent]), Collects())

    planned, blocked = await engine.plan_all([candidate], actor_id=user_id)

    assert planned[candidate.id] == []
    assert blocked == {candidate.id}


# --- SimpleContradictionDetector reads the value, not the ciphertext --------


class _Row:
    """A stand-in for a stored row whose content column holds AES-GCM ciphertext.

    `MemoryRepository.create` seals `content` with a random nonce, so two rows
    holding byte-identical plaintext never compare equal in that column. Reading
    `content` directly made the "content differs" half of the detector
    permanently true and left a bare title ratio, which fired on any two
    memories sharing a headline.
    """

    def __init__(self, title: str, plaintext: str, *, seal: bool = True) -> None:
        self.title = title
        self.structured_data: dict[str, Any] = {}
        self.content = f"enc:v1:{hex(abs(hash(plaintext)))}:{len(plaintext)}" if seal else plaintext
        self._plaintext = plaintext

    @property
    def plaintext_content(self) -> str:
        return self._plaintext


async def test_simple_detector_compares_plaintext_not_ciphertext() -> None:
    detector = SimpleContradictionDetector()
    same = _Row("Preferred language", "The user prefers Python.")

    # Identical plaintext, two independently sealed ciphertexts.
    assert not await detector.contradicts(same, _Row("Preferred language", "The user prefers Python."))

    different = _Row("Preferred language", "The user prefers Rust.")
    assert await detector.contradicts(different, same)


async def test_simple_detector_needs_a_value_difference_not_just_a_similar_title() -> None:
    detector = SimpleContradictionDetector()
    left = _Row("Employer", "The user works at Contoso.", seal=False)

    # Same headline, same value, nothing to reconcile.
    assert not await detector.contradicts(
        _Row("Employer", "The user works at Contoso.", seal=False),
        left,
    )
    # A different value under the same headline is the case this path exists for.
    assert await detector.contradicts(_Row("Employer", "The user works at Fabrikam."), left)
    # A different value under a different headline is not: that is why the title
    # gate is still here on the path that has no slot to narrow by.
    assert not await detector.contradicts(
        _Row("Editor", "The user uses vim.", seal=False),
        left,
    )


# --- the regression metric: superseded / total -----------------------------

# The shape of the ingest that produced the damage: "the user" as the subject,
# coarse snake_case verbs as the predicate, and mostly unrelated objects. Four
# of these ten share a predicate on purpose.
_INGEST_FIXTURES: list[dict[str, str]] = [
    {"subject": "the user", "predicate": "uses", "obj": "multiplication"},
    {"subject": "the user", "predicate": "uses", "obj": "function_15"},
    {"subject": "the user", "predicate": "uses", "obj": "the command line"},
    {"subject": "the user", "predicate": "uses", "obj": "spreadsheets"},
    {"subject": "the user", "predicate": "has", "obj": "an api key"},
    {"subject": "the user", "predicate": "has", "obj": "a code snippet"},
    {"subject": "the user", "predicate": "prefers", "obj": "dark mode"},
    {"subject": "the user", "predicate": "prefers", "obj": "tabs over spaces"},
    {"subject": "the user", "predicate": "based_in", "obj": "lisbon"},
    {"subject": "the user", "predicate": "expected_expiry", "obj": "2026-01-31"},
]


async def test_ingest_shaped_fixtures_supersede_under_ten_percent() -> None:
    """The ratio that was wrong, asserted directly.

    Under the old digest these ten rows resolved to five slots -- `uses` x4,
    `has` x2, `prefers` x2, and two singletons -- and every arrival after the
    first in a slot closed its predecessor: 5 of 10 rows superseded, 50%, and the
    ten facts reachable from retrieval collapsed onto five. The target is under
    10%, and with ten fixtures that means no arrival may close a sibling at all
    -- which is the claim, not a coincidence of the sample.
    """
    organization_id, user_id = uuid4(), uuid4()
    repository = SlotRepository(rows=[])
    engine = TruthMaintenanceEngine(repository, Collects())

    superseded = 0
    total = 0
    for fixture in _INGEST_FIXTURES:
        memory = extracted(**fixture)
        record = MemoryRecord(
            id=uuid4(),
            user_id=user_id,
            organization_id=organization_id,
            memory_type=memory.memory_type.value,
            title=memory.title,
            content=memory.content,
            source_type=memory.source_type.value,
            structured_data=memory.structured_data,
            confidence=1.0,
            importance=0.5,
            fact_key=key_of(memory),
            valid_from=datetime.now(UTC).replace(tzinfo=None),
            valid_to=None,
        )
        total += 1
        planned = await engine.plan(record, actor_id=user_id)
        superseded += len(planned)
        repository.rows.append(record)

    assert total == len(_INGEST_FIXTURES)
    assert superseded / total < 0.10
    # And the facts themselves are all still current, which was the point.
    assert len([row for row in repository.rows if row.valid_to is None]) == total

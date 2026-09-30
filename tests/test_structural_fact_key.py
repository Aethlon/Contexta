"""Tests for the structural fact key that names a fact slot.

A slot is the whole assertion: canonicalised subject, predicate, optional context
and object, hashed to `sfx2:<sha256>`. Two memories that state the same fact
however they are worded share a key; two memories that state *different* facts
never do, which is what keeps `uq_memory_record_current_fact_slot` from picking a
winner among mutually exclusive facts. Memories whose extraction carried no
usable triple keep the legacy text-hash key, so rows written before this change
stay readable and a model that omits the field never costs a memory.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from contexta.core.extraction.deduplication import MemoryDeduplicator
from contexta.core.extraction.worker import ExtractionWorker, normalize_structured_fact
from contexta.core.pipeline import fact_key_for_memory
from contexta.core.schemas import ExtractedMemory, ObservationPayload
from contexta.core.truth.maintenance import TruthMaintenanceEngine
from contexta.core.truth.service import fact_value
from contexta.core.types import MemoryType, SourceType
from contexta.models.memory import MemoryRecord
from contexta.models.version import MemoryVersion

_LEGACY_KEY = re.compile(r"^[0-9a-f]{64}$")


def slot_key(
    subject: str,
    predicate: str,
    obj: str,
    context: str | None = None,
) -> str:
    fact: dict[str, str] = {"subject": subject, "predicate": predicate, "object": obj}
    if context is not None:
        fact["context"] = context
    return fact_key_for_memory(structured_fact(fact), uuid4(), uuid4())


def structured_fact(fact: dict[str, str]) -> ExtractedMemory:
    return ExtractedMemory(
        memory_type=MemoryType.FACT,
        source_type=SourceType.USER_EXPLICIT,
        title="Fact",
        content="Prose that says nothing about the slot.",
        structured_data={"fact": dict(fact), "fact_value": fact["object"]},
    )


def named_slot_fact(slot: str, value: str) -> ExtractedMemory:
    """A memory whose extractor named the slot itself, value excluded.

    The one path where two different values still land in one slot, so it is the
    path that has to keep working supersession.
    """
    return ExtractedMemory(
        memory_type=MemoryType.FACT,
        source_type=SourceType.USER_EXPLICIT,
        title="Compensation",
        content=f"The user's salary is {value}.",
        structured_data={"fact_key": slot, "fact_value": value, "status": "current"},
    )


def key_of(memory: ExtractedMemory, organization_id: UUID, user_id: UUID) -> str:
    return fact_key_for_memory(memory, organization_id, user_id)


# --- the triple derives one stable key -----------------------------------


def test_same_fact_in_different_prose_yields_one_key() -> None:
    organization_id, user_id = uuid4(), uuid4()
    first = ExtractedMemory(
        memory_type=MemoryType.FACT,
        source_type=SourceType.USER_EXPLICIT,
        title="Home city",
        content="Fatima Okafor lives in Lisbon.",
        structured_data={
            "fact": {"subject": "Fatima Okafor", "predicate": "lives_in", "object": "Lisbon"},
            "fact_value": "Lisbon",
        },
    )
    # Same slot, stated with different casing, spacing and surrounding prose.
    second = ExtractedMemory(
        memory_type=MemoryType.FACT,
        source_type=SourceType.USER_EXPLICIT,
        title="Where Fatima lives these days",
        content="As of this spring Fatima Okafor is living in  Lisbon, Portugal.",
        structured_data={
            "fact": {"subject": "  fatima   OKAFOR ", "predicate": "LIVES_IN", "object": "lisbon"},
            "fact_value": "lisbon",
        },
    )

    assert key_of(first, organization_id, user_id) == key_of(second, organization_id, user_id)
    assert first.content != second.content


def test_distinct_slots_do_not_collide() -> None:
    assert slot_key("Fatima Okafor", "lives_in", "Lisbon") != slot_key("Fatima Okafor", "employer", "Lisbon")
    assert slot_key("Fatima Okafor", "lives_in", "Lisbon") != slot_key("Marcus Silva", "lives_in", "Lisbon")
    # The object is part of the slot, so two mutually exclusive values of one
    # attribute are two slots. Under `sfx1:` they shared one, and whichever
    # arrived second closed the first: 28 of 46 stored rows were closed that way
    # in a measured ingest, 8 of 10 sampled pairs being unrelated facts.
    assert slot_key("Fatima Okafor", "lives_in", "Lisbon") != slot_key("Fatima Okafor", "lives_in", "Berlin")
    # A context qualifier scopes a slot that is ambiguous without it.
    assert slot_key("Atlas", "version", "2.1") != slot_key("Atlas", "version", "2.1", context="staging")


def test_structural_key_is_distinguishable_from_legacy_text_hash() -> None:
    organization_id, user_id = uuid4(), uuid4()
    structural = key_of(
        structured_fact({"subject": "Fatima Okafor", "predicate": "lives_in", "object": "Lisbon"}),
        organization_id,
        user_id,
    )
    legacy = key_of(
        ExtractedMemory(
            memory_type=MemoryType.FACT,
            source_type=SourceType.USER_EXPLICIT,
            title="Fact",
            content="No triple at all.",
        ),
        organization_id,
        user_id,
    )

    assert not _LEGACY_KEY.match(structural)
    assert _LEGACY_KEY.match(legacy)


def test_flat_sibling_triple_from_the_real_extractor_yields_a_structural_key() -> None:
    # The fine-tuned extractor emits the triple as bare siblings of
    # structured_data, not under a `fact` key. A nested-only lookup missed
    # every real row, so 100% of structural keys silently fell back to the
    # legacy text hash and truth maintenance had nothing to reconcile.
    organization_id, user_id = uuid4(), uuid4()
    item = {
        "structured_data": {
            "subject": "the user",
            "predicate": "prefers",
            "object": "dark mode",
            "status": "current",
            "polarity": "positive",
            "temporal": {"basis": "ingestion_fallback"},
        }
    }

    fact = normalize_structured_fact(item)
    assert fact == {"subject": "the user", "predicate": "prefers", "object": "dark mode"}

    memory = ExtractedMemory(
        memory_type=MemoryType.PREFERENCE,
        source_type=SourceType.AGENT_INFERENCE,
        title="Prefers dark mode",
        content="The user prefers dark mode.",
        structured_data={**item["structured_data"], "fact": fact},
    )
    key = fact_key_for_memory(memory, organization_id, user_id)

    assert key.startswith("sfx2:")
    assert not _LEGACY_KEY.match(key)


def test_partial_flat_triple_still_falls_back_instead_of_guessing() -> None:
    # A slot needs all three parts. Two of three must not be guessed into a
    # key, or an unrelated memory can collide with a stored fact.
    assert normalize_structured_fact({"structured_data": {"subject": "u", "object": "dark mode"}}) is None
    assert normalize_structured_fact({"structured_data": {"subject": "u", "predicate": "prefers"}}) is None
    assert normalize_structured_fact({"structured_data": {"polarity": "positive", "status": "ok"}}) is None


# --- a corrected value no longer collapses into the slot it corrects -------


def test_distinct_values_of_one_attribute_occupy_distinct_slots() -> None:
    """The regression this file was written against, inverted.

    Under `sfx1:` a corrected value hashed onto the same slot as the value it
    corrected, which is what let the one-current-row index retire the incumbent.
    That is now the opposite: the two coexist, and deciding which of them is
    current is the truth engine's job -- on the value comparability gate and on
    the extractor's own `status`, not on a digest collision.
    """
    organization_id, user_id = uuid4(), uuid4()
    lisbon = structured_fact({"subject": "Fatima Okafor", "predicate": "lives_in", "object": "Lisbon"})
    berlin = structured_fact({"subject": "Fatima Okafor", "predicate": "lives_in", "object": "Berlin"})

    # Different values, so the two rows can both stay current...
    assert key_of(lisbon, organization_id, user_id) != key_of(berlin, organization_id, user_id)
    # ...and the value each one asserts is still what the truth engine compares.
    assert fact_value(lisbon) != fact_value(berlin)


@dataclass
class SlotRepository:
    """A tenant-scoped stand-in exposing only the slot lookup truth maintenance uses."""

    rows: list[MemoryRecord]
    superseded: list[tuple[UUID, datetime]] = field(default_factory=list)

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
                self.superseded.append((record_id, valid_to))
                return 1
        return 0


@dataclass
class Collects:
    records: list[Any] = field(default_factory=list)

    async def create(self, record: Any) -> Any:
        self.records.append(record)
        return record


def record_for(
    extracted: ExtractedMemory,
    organization_id: UUID,
    user_id: UUID,
    fact_key: str,
) -> MemoryRecord:
    now = datetime.now(UTC)
    return MemoryRecord(
        id=uuid4(),
        user_id=user_id,
        organization_id=organization_id,
        memory_type=extracted.memory_type.value,
        title=extracted.title,
        content=extracted.content,
        source_type=extracted.source_type.value,
        structured_data=extracted.structured_data,
        confidence=1.0,
        importance=0.5,
        fact_key=fact_key,
        valid_from=now,
        valid_to=None,
    )


async def test_corrected_value_supersedes_the_incumbent_row() -> None:
    """Supersession still happens -- on the slot the extractor named.

    With the object in the digest, a correction of a free-form attribute no
    longer shares a slot with what it corrects. The path that still has two
    values inside one slot is an extractor-supplied `fact_key`, and the value has
    to be comparable for the close to be allowed at all, so the two amounts here
    are both currency on purpose.
    """
    organization_id, user_id = uuid4(), uuid4()
    old_extracted = named_slot_fact("the user|salary", "$45,000")
    new_extracted = named_slot_fact("the user|salary", "$93,000")
    old = record_for(old_extracted, organization_id, user_id, key_of(old_extracted, organization_id, user_id))
    new = record_for(new_extracted, organization_id, user_id, key_of(new_extracted, organization_id, user_id))

    assert old.fact_key == new.fact_key

    repository = SlotRepository(rows=[old])
    versions = Collects()
    engine = TruthMaintenanceEngine(repository, versions)

    result = await engine.apply(new, actor_id=user_id)

    assert len(result) == 1
    assert result[0].old_memory_id == old.id
    assert old.valid_to == result[0].valid_to
    assert isinstance(versions.records[0], MemoryVersion)
    assert versions.records[0].superseded_by_id == new.id


async def test_restatement_of_the_same_value_is_not_stored_twice() -> None:
    organization_id, user_id = uuid4(), uuid4()
    payload = ObservationPayload(
        user_id=user_id,
        organization_id=organization_id,
        session_id=uuid4(),
        messages=[{"role": "user", "content": "Fatima moved."}],
    )
    incumbent_extracted = structured_fact(
        {"subject": "Fatima Okafor", "predicate": "lives_in", "object": "Lisbon"}
    )
    repeat_extracted = structured_fact(
        {"subject": "fatima  Okafor", "predicate": "lives_in", "object": "lisbon"}
    )
    incumbent = record_for(
        incumbent_extracted, organization_id, user_id, key_of(incumbent_extracted, organization_id, user_id)
    )

    class Repo(SlotRepository):
        async def update_by_id(self, record_id: UUID, values: dict) -> int:
            return 1

    repository = Repo(rows=[incumbent])
    deduplicator = MemoryDeduplicator(repository)

    result = await deduplicator.deduplicate(
        payload,
        repeat_extracted,
        fact_key=key_of(repeat_extracted, organization_id, user_id),
    )

    assert result.action == "discard"
    assert result.existing_id == incumbent.id


# --- a missing or malformed triple degrades to the legacy key -------------


def test_memory_without_a_structured_fact_keeps_the_legacy_key() -> None:
    organization_id, user_id = uuid4(), uuid4()
    memory = ExtractedMemory(
        memory_type=MemoryType.FACT,
        source_type=SourceType.USER_EXPLICIT,
        title="Prefers Python",
        content="The user prefers Python for backend work.",
        tags=["python"],
    )

    key = key_of(memory, organization_id, user_id)

    assert _LEGACY_KEY.match(key)
    assert key == key_of(memory, organization_id, user_id)
    # The legacy key still varies with the wording, which is why it is a fallback.
    reworded = memory.model_copy(update={"content": "The user really prefers Python."})
    assert key_of(reworded, organization_id, user_id) != key


@pytest.mark.parametrize(
    "structured",
    [
        None,
        {},
        {"fact": {}},
        {"fact": {"subject": "Fatima Okafor"}},
        {"fact": {"subject": "Fatima Okafor", "predicate": "lives_in"}},
        {"fact": {"predicate": "lives_in", "object": "Lisbon"}},
        {"fact": {"subject": "   ", "predicate": "lives_in", "object": "Lisbon"}},
        {"fact": "Fatima Okafor lives in Lisbon"},
        {"fact": {"subject": ["a"], "predicate": "b", "object": "c"}},
    ],
)
def test_partial_or_malformed_triples_fall_back_to_the_legacy_key(structured: dict | None) -> None:
    organization_id, user_id = uuid4(), uuid4()
    memory = ExtractedMemory(
        memory_type=MemoryType.FACT,
        source_type=SourceType.USER_EXPLICIT,
        title="Fact",
        content="Something worth remembering.",
        structured_data=structured,
    )

    assert _LEGACY_KEY.match(key_of(memory, organization_id, user_id))


# --- the extraction worker lifts the triple out of the model response ------


class RecordingLLM:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.system_prompt: str | None = None

    async def complete_json(self, prompt: str, system_prompt: str | None = None) -> dict:
        self.system_prompt = system_prompt
        return self.response


def payload() -> ObservationPayload:
    return ObservationPayload(
        user_id=uuid4(),
        organization_id=uuid4(),
        session_id=uuid4(),
        messages=[{"role": "user", "content": "Fatima Okafor moved to Berlin."}],
    )


async def test_worker_keeps_the_triple_and_publishes_the_value() -> None:
    llm = RecordingLLM(
        {
            "memories": [
                {
                    "memory_type": "fact",
                    "source_type": "user_explicit",
                    "title": "Deploy target",
                    "content": "The billing service deploys to eu-west-1.",
                    "structured_data": {
                        "fact": {
                            "subject": "billing service",
                            "predicate": "deploys_to",
                            "object": "eu-west-1",
                        }
                    },
                }
            ]
        }
    )

    memories = await ExtractionWorker(llm_service=llm).extract(payload())

    assert len(memories) == 1
    fact = memories[0].structured_data["fact"]
    assert fact == {
        "subject": "billing service",
        "predicate": "deploys_to",
        "object": "eu-west-1",
    }
    assert memories[0].structured_data["fact_value"] == "eu-west-1"
    assert "structured_data.fact" in llm.system_prompt


async def test_worker_accepts_the_triple_at_the_top_level() -> None:
    llm = RecordingLLM(
        {
            "memories": [
                {
                    "memory_type": "fact",
                    "source_type": "user_explicit",
                    "title": "Deploy target",
                    "content": "The billing service deploys to eu-west-1.",
                    "fact": {
                        "subject": "billing service",
                        "predicate": "deploys_to",
                        "object": "eu-west-1",
                    },
                }
            ]
        }
    )

    memories = await ExtractionWorker(llm_service=llm).extract(payload())

    assert memories[0].structured_data["fact_value"] == "eu-west-1"


async def test_worker_stores_a_memory_whose_model_omitted_the_fact() -> None:
    llm = RecordingLLM(
        {
            "memories": [
                {
                    "memory_type": "preference",
                    "source_type": "user_explicit",
                    "title": "Prefers Python",
                    "content": "Prefers Python for backend work.",
                }
            ]
        }
    )

    memories = await ExtractionWorker(llm_service=llm).extract(payload())

    assert len(memories) == 1
    assert "fact" not in (memories[0].structured_data or {})
    assert memories[0].content == "Prefers Python for backend work."


async def test_worker_keeps_a_memory_whose_fact_is_partial() -> None:
    llm = RecordingLLM(
        {
            "memories": [
                {
                    "memory_type": "fact",
                    "source_type": "user_explicit",
                    "title": "Deploy target",
                    "content": "The billing service deploys to eu-west-1.",
                    "structured_data": {"fact": {"subject": "billing service", "object": "eu-west-1"}},
                }
            ]
        }
    )

    memories = await ExtractionWorker(llm_service=llm).extract(payload())

    assert len(memories) == 1
    assert "fact_value" not in (memories[0].structured_data or {})


def test_extraction_json_schema_advertises_the_fact_triple() -> None:
    schema = ExtractionWorker._extraction_json_schema()
    properties = schema["properties"]["memories"]["items"]["properties"]
    fact = properties["structured_data"]["properties"]["fact"]

    assert fact["required"] == ["subject", "predicate", "object"]
    assert set(fact["properties"]) == {"subject", "predicate", "object", "context"}


def test_normalize_structured_fact_ignores_unusable_payloads() -> None:
    assert normalize_structured_fact({}) is None
    assert normalize_structured_fact({"structured_data": {"fact": {"subject": "a"}}}) is None
    assert normalize_structured_fact({"structured_data": "not-a-mapping"}) is None
    assert normalize_structured_fact(
        {"structured_data": {"fact": {"subject": "a", "predicate": "b", "object": 7}}}
    ) == {"subject": "a", "predicate": "b", "object": "7"}


# --- the triple must not become a redaction bypass ------------------------


def person_fact(object_value: str, *, content: str | None = None, subject: str = "Fatima Okafor") -> dict:
    return {
        "memories": [
            {
                "memory_type": "fact",
                "source_type": "user_explicit",
                "title": "Home city",
                "content": content or f"{subject} lives in {object_value}.",
                "entities": [subject],
                "structured_data": {
                    "fact": {
                        "subject": subject,
                        "predicate": "lives_in",
                        "object": object_value,
                    }
                },
            }
        ]
    }


async def test_fact_subject_is_pseudonymized_like_the_content() -> None:
    memories = await ExtractionWorker(llm_service=RecordingLLM(person_fact("Lisbon"))).extract(payload())

    fact = memories[0].structured_data["fact"]
    assert "Fatima Okafor" not in json.dumps(memories[0].structured_data)
    assert fact["subject"].startswith("[PERSON_")
    # The token matches the one the redacted prose uses, so the two agree.
    assert fact["subject"] in memories[0].content
    assert fact["object"] == "Lisbon"


async def test_fact_slot_stays_one_slot_across_a_pseudonymized_restatement() -> None:
    organization_id, user_id = uuid4(), uuid4()
    first = await ExtractionWorker(
        llm_service=RecordingLLM(
            person_fact("Lisbon", content="Fatima Okafor lives in Lisbon.")
        )
    ).extract(payload())
    second = await ExtractionWorker(
        llm_service=RecordingLLM(
            person_fact("Lisbon", content="These days Fatima Okafor is living in Lisbon, Portugal.")
        )
    ).extract(payload())

    # The name resolves to a different token in each scan, so the slot can only
    # match if the pseudonymization is anchored to the prose of its own memory.
    assert first[0].content != second[0].content
    assert key_of(first[0], organization_id, user_id) == key_of(second[0], organization_id, user_id)


async def test_fact_object_is_pseudonymized_when_it_names_a_person() -> None:
    llm = RecordingLLM(
        {
            "memories": [
                {
                    "memory_type": "relationship",
                    "source_type": "user_explicit",
                    "title": "Reporting line",
                    "content": "Fatima Okafor manages Marcus Silva.",
                    "structured_data": {
                        "fact": {
                            "subject": "Fatima Okafor",
                            "predicate": "manages",
                            "object": "Marcus Silva",
                        }
                    },
                }
            ]
        }
    )

    memories = await ExtractionWorker(llm_service=llm).extract(payload())

    fact = memories[0].structured_data["fact"]
    assert "Fatima Okafor" not in json.dumps(memories[0].structured_data)
    assert "Marcus Silva" not in json.dumps(memories[0].structured_data)
    assert fact["subject"].startswith("[PERSON_")
    assert fact["object"].startswith("[PERSON_")
    # Two distinct people must not collapse onto one token.
    assert fact["subject"] != fact["object"]
    assert memories[0].structured_data["fact_value"] == fact["object"]


async def test_slot_survives_a_subject_the_pii_pattern_would_miss() -> None:
    """The soft-name pattern only matches Capitalised Capitalised text.

    A subject written as "  fatima   OKAFOR " escapes pseudonymization while the
    prose beside it is redacted, which would store the same person twice under
    two spellings and split one fact slot in two.
    """
    organization_id, user_id = uuid4(), uuid4()
    canonical = await ExtractionWorker(
        llm_service=RecordingLLM(person_fact("Lisbon", content="Fatima Okafor lives in Lisbon."))
    ).extract(payload())
    odd_casing = await ExtractionWorker(
        llm_service=RecordingLLM(
            person_fact(
                "Lisbon",
                subject="  fatima   OKAFOR ",
                content="Fatima Okafor lives in Lisbon.",
            )
        )
    ).extract(payload())

    assert canonical[0].structured_data["fact"]["subject"].startswith("[PERSON_")
    assert odd_casing[0].structured_data["fact"]["subject"].startswith("[PERSON_")
    assert "fatima" not in json.dumps(odd_casing[0].structured_data).casefold().replace("person_1", "")
    assert key_of(canonical[0], organization_id, user_id) == key_of(odd_casing[0], organization_id, user_id)


async def test_structured_data_never_keeps_the_pre_redaction_text() -> None:
    """`structured_data` carries verbatim copies of the source text.

    `temporal.original_text` / `temporal.normalized_text` are written during
    parsing, before the content is redacted, so redacting only `content` left the
    real name in the same row as `[PERSON_1]`.
    """
    llm = RecordingLLM(
        {
            "memories": [
                {
                    "memory_type": "fact",
                    "source_type": "user_explicit",
                    "title": "Home city",
                    "content": "Fatima Okafor lives in Lisbon.",
                    "structured_data": {
                        "fact": {
                            "subject": "Fatima Okafor",
                            "predicate": "lives_in",
                            "object": "Lisbon",
                        }
                    },
                }
            ]
        }
    )

    memories = await ExtractionWorker(llm_service=llm).extract(payload())

    assert "Fatima Okafor" not in json.dumps(memories[0].structured_data)
    temporal = memories[0].structured_data["temporal"]
    assert "Fatima Okafor" not in temporal["original_text"]
    assert "Fatima Okafor" not in temporal["normalized_text"]
    assert "Fatima Okafor" not in memories[0].original_text
    assert "Fatima Okafor" not in memories[0].normalized_text
    # The token the temporal copy carries is the one the prose uses.
    assert memories[0].content.split()[0] in temporal["normalized_text"]


async def test_fact_carrying_a_direct_identifier_is_dropped_not_stored() -> None:
    llm = RecordingLLM(
        {
            "memories": [
                {
                    "memory_type": "fact",
                    "source_type": "user_explicit",
                    "title": "Contact",
                    "content": "The support contact is on file.",
                    "structured_data": {
                        "fact": {
                            "subject": "Support",
                            "predicate": "email",
                            "object": "ops@example.com",
                        }
                    },
                }
            ]
        }
    )

    memories = await ExtractionWorker(llm_service=llm).extract(payload())

    # The memory is still stored; it just falls back to the legacy key.
    assert len(memories) == 1
    structured = memories[0].structured_data
    assert "fact" not in structured
    assert "fact_value" not in structured
    assert "ops@example.com" not in json.dumps(structured)
    assert _LEGACY_KEY.match(key_of(memories[0], uuid4(), uuid4()))

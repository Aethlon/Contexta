"""Regression tests for degenerate extraction bodies and no-op dedup merges.

Defect A: the fine-tuned extractor cannot always quote a complete sentence, so it
emits the subject string it was told to use -- literally ``"the user"`` -- or an
echo of the object/predicate. 8 of 130 rows on a live ingest had
``content == "the user"``. A synthesised title hid it.

Defect B: ``MemoryDeduplicator`` reported ``action="merge"`` for a merge that
concatenated nothing, and the pipeline skips storing on ``"merge"``, so the
incoming memory was silently dropped.
"""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import httpx
import pytest

from contexta.config.settings import Settings
from contexta.core.extraction.deduplication import MemoryDeduplicator
from contexta.core.schemas import ExtractedMemory, ObservationPayload
from contexta.core.types import MemoryType, SourceType
from contexta.services.llm import LLMService


class FakeResponse:
    """Minimal stand-in for an httpx response carrying gold claims."""

    def __init__(self, claims: list[dict]) -> None:
        self._claims = claims

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"claims": self._claims}


async def extract_claims(monkeypatch, claims: list[dict]) -> list[dict]:
    """Run the inference-server adapter over ``claims`` and return its memories."""
    response = FakeResponse(claims)

    async def fake_post(*args, **kwargs):
        return response

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    service = LLMService(Settings())
    return await service._extract_via_inference_server("user: I moved to Berlin.")


# ── Defect A: degenerate content ──────────────────────────────────────────────


async def test_text_equal_to_subject_is_not_stored_as_content(monkeypatch) -> None:
    memories = await extract_claims(
        monkeypatch,
        [
            {
                "text": "the user",
                "subject": "the user",
                "predicate": "distinguished_value",
                "object": "112,000 USD",
            }
        ],
    )

    assert len(memories) == 1
    assert memories[0]["content"].lower() != "the user"
    assert "112,000 USD" in memories[0]["content"]


async def test_degenerate_body_with_valid_triple_keeps_the_fact(monkeypatch) -> None:
    """Prefer falling back over dropping: the fact value is worth keeping."""
    memories = await extract_claims(
        monkeypatch,
        [
            {
                "text": "the user",
                "subject": "the user",
                "predicate": "distinguished_value",
                "object": "112,000 USD",
            }
        ],
    )

    assert len(memories) == 1
    memory = memories[0]
    assert memory["content"] == "the user distinguished_value 112,000 USD"
    assert memory["title"] == "the user distinguished_value 112,000 USD"
    assert memory["structured_data"]["object"] == "112,000 USD"


async def test_object_echo_body_falls_back_to_summary(monkeypatch) -> None:
    memories = await extract_claims(
        monkeypatch,
        [{"text": "6543", "subject": "the user", "predicate": "has_port", "object": "6543"}],
    )

    assert len(memories) == 1
    assert memories[0]["content"] == "the user has_port 6543"


async def test_predicate_echo_body_falls_back_to_summary(monkeypatch) -> None:
    memories = await extract_claims(
        monkeypatch,
        [{"text": "is owned by", "subject": "the user", "predicate": "owned", "object": "PERSON_2"}],
    )

    assert len(memories) == 1
    assert memories[0]["content"] == "the user owned PERSON_2"


async def test_empty_text_and_empty_triple_produces_no_memory(monkeypatch) -> None:
    memories = await extract_claims(
        monkeypatch,
        [
            {"text": "", "subject": "the user", "predicate": "", "object": ""},
            {"text": "the user", "subject": "the user", "predicate": "", "object": ""},
            {"text": None, "subject": "the user", "predicate": "", "object": ""},
        ],
    )

    assert memories == []


async def test_normal_claim_is_unchanged(monkeypatch) -> None:
    """The good path must not regress: title synthesised, content verbatim."""
    memories = await extract_claims(
        monkeypatch,
        [
            {
                "text": "I prefer Python for backend work.",
                "subject": "the user",
                "predicate": "prefers",
                "object": "Python for backend work",
                "memory_type": "preference",
            }
        ],
    )

    assert len(memories) == 1
    memory = memories[0]
    assert memory["content"] == "I prefer Python for backend work."
    assert memory["title"] == "the user prefers Python for backend work"
    assert memory["memory_type"] == "preference"


async def test_short_verbatim_sentence_with_no_triple_is_preserved(monkeypatch) -> None:
    """A real quote with no usable triple must not be replaced by the subject."""
    memories = await extract_claims(
        monkeypatch,
        [
            {
                "text": "I moved to Berlin last spring.",
                "subject": "the user",
                "predicate": "",
                "object": "",
            }
        ],
    )

    assert len(memories) == 1
    assert memories[0]["content"] == "I moved to Berlin last spring."
    # Title must not collapse to the restated subject.
    assert memories[0]["title"] == "I moved to Berlin last spring."


ADVERSARIAL_CLAIMS: list[dict] = [
    # text == subject, the exact shape of the 8 measured "the user" rows
    {"text": "the user", "subject": "the user", "predicate": "prefers", "object": "tea"},
    {"text": "The User", "subject": "the user", "predicate": "prefers", "object": "tea"},
    {"text": "  the user.  ", "subject": "the user", "predicate": "prefers", "object": "tea"},
    # object / predicate echoes
    {"text": "6543", "subject": "the user", "predicate": "has_port", "object": "6543"},
    {"text": "is owned by", "subject": "the user", "predicate": "owned", "object": "PERSON_2"},
    {"text": "112,000 USD", "subject": "the user", "predicate": "portfolio_value", "object": "112,000 USD"},
    # below the character floor
    {"text": "no", "subject": "the user", "predicate": "rejected", "object": "v1 architecture"},
    {"text": "12", "subject": "the user", "predicate": "seat_count", "object": "12"},
    # degenerate body, no triple at all
    {"text": "the user", "subject": "the user", "predicate": "", "object": ""},
    {"text": "", "subject": "the user", "predicate": "", "object": ""},
    {"text": "hmm", "subject": "", "predicate": "", "object": ""},
    # half-formed triples
    {"text": "the user", "subject": "the user", "predicate": "based_in", "object": ""},
    {"text": "Berlin", "subject": "", "predicate": "", "object": "Berlin"},
    # healthy claims, must pass through untouched
    {
        "text": "My portfolio is worth roughly 112,000 USD right now.",
        "subject": "the user",
        "predicate": "portfolio_value",
        "object": "112,000 USD",
    },
    {
        "text": "We decided to standardise on PostgreSQL for the primary store.",
        "subject": "the team",
        "predicate": "standardised_on",
        "object": "PostgreSQL",
    },
]


@pytest.mark.parametrize("claim", ADVERSARIAL_CLAIMS, ids=range(len(ADVERSARIAL_CLAIMS)))
async def test_sweep_emits_no_degenerate_body(monkeypatch, claim: dict) -> None:
    memories = await extract_claims(monkeypatch, [claim])

    subject = str(claim.get("subject") or "the user").strip()
    for memory in memories:
        content = memory["content"]
        assert content, "a produced memory must never have empty content"
        assert len(content) >= 3
        assert content.strip().casefold() != subject.casefold()
        assert memory["title"].strip()


async def test_sweep_preserves_every_complete_triple(monkeypatch) -> None:
    """A degenerate body never costs the fact value of an intact triple."""
    claims = [claim for claim in ADVERSARIAL_CLAIMS if claim.get("predicate") and claim.get("object")]

    memories = await extract_claims(monkeypatch, claims)

    assert len(memories) == len(claims)
    assert all(memory["content"].strip() for memory in memories)


async def test_sweep_drops_claims_with_neither_body_nor_triple(monkeypatch) -> None:
    claims = [
        claim for claim in ADVERSARIAL_CLAIMS if not (claim.get("predicate") and claim.get("object"))
    ]

    assert claims, "fixtures must include incomplete-triple claims"
    assert await extract_claims(monkeypatch, claims) == []


# ── Defect B: dedup merge must actually merge ─────────────────────────────────


@dataclass
class ExistingMemory:
    id: UUID
    user_id: UUID
    organization_id: UUID
    memory_type: str
    title: str
    content: str
    structured_data: dict | None = None
    tags: list[str] | None = None
    valid_to: object | None = None


@dataclass
class FakeMemoryRepository:
    records: list[ExistingMemory]
    updates: list[tuple[UUID, dict]] = field(default_factory=list)

    async def get_by_type(self, user_id, memory_type, *, offset: int = 0, limit: int = 100):
        return [
            record
            for record in self.records
            if record.user_id == user_id and record.memory_type == memory_type.value
        ]

    async def update_by_id(self, record_id: UUID, values: dict) -> int:
        self.updates.append((record_id, values))
        return 1


class FixedSimilarity:
    def __init__(self, score: float) -> None:
        self.score = score

    async def similarity(self, left: str, right: str) -> float:
        return self.score


@pytest.fixture
def payload() -> ObservationPayload:
    return ObservationPayload(
        user_id=uuid4(),
        organization_id=uuid4(),
        session_id=uuid4(),
        messages=[{"role": "user", "content": "Remember I prefer Python."}],
    )


def incoming(content: str = "The user prefers Python.") -> ExtractedMemory:
    return ExtractedMemory(
        memory_type=MemoryType.PREFERENCE,
        source_type=SourceType.USER_EXPLICIT,
        title="Prefers Python",
        content=content,
        tags=["python"],
    )


async def test_noop_merge_does_not_report_merge_or_lose_the_memory(
    payload: ObservationPayload,
) -> None:
    """The measured shape: two ``"the user"`` bodies, one of them silently lost."""
    existing = ExistingMemory(
        id=uuid4(),
        user_id=payload.user_id,
        organization_id=payload.organization_id,
        memory_type=MemoryType.PREFERENCE.value,
        title="the user distinguished_value 112,000 USD",
        content="the user",
    )
    repo = FakeMemoryRepository(records=[existing])
    deduplicator = MemoryDeduplicator(repo, FixedSimilarity(0.88))

    result = await deduplicator.deduplicate(payload, incoming("the user"))

    assert result.action == "store"
    assert result.memory is not None
    assert result.memory.content == "the user"
    assert repo.updates == []


async def test_substring_incoming_does_not_report_merge(payload: ObservationPayload) -> None:
    existing = ExistingMemory(
        id=uuid4(),
        user_id=payload.user_id,
        organization_id=payload.organization_id,
        memory_type=MemoryType.PREFERENCE.value,
        title="Prefers Python",
        content="The user prefers Python for all backend work.",
    )
    repo = FakeMemoryRepository(records=[existing])
    deduplicator = MemoryDeduplicator(repo, FixedSimilarity(0.9))

    result = await deduplicator.deduplicate(payload, incoming("The user prefers Python"))

    assert result.action == "store"
    assert repo.updates == []


async def test_genuine_merge_still_merges_and_grows(payload: ObservationPayload) -> None:
    existing = ExistingMemory(
        id=uuid4(),
        user_id=payload.user_id,
        organization_id=payload.organization_id,
        memory_type=MemoryType.PREFERENCE.value,
        title="Python preference",
        content="The user likes Python.",
        structured_data={"language": "python"},
        tags=["backend"],
    )
    repo = FakeMemoryRepository(records=[existing])
    deduplicator = MemoryDeduplicator(repo, FixedSimilarity(0.9))

    result = await deduplicator.deduplicate(payload, incoming())

    assert result.action == "merge"
    assert result.existing_id == existing.id
    merged = repo.updates[0][1]["content"]
    assert len(merged) > len(existing.content)
    assert "The user likes Python." in merged
    assert "The user prefers Python." in merged


async def test_noop_merge_writes_no_pre_merge_version(payload: ObservationPayload) -> None:
    """A merge that does not happen must not pollute truth-maintenance lineage."""

    class RecordingVersions:
        def __init__(self) -> None:
            self.created: list[object] = []

        async def create(self, record):
            self.created.append(record)
            return record

    existing = ExistingMemory(
        id=uuid4(),
        user_id=payload.user_id,
        organization_id=payload.organization_id,
        memory_type=MemoryType.PREFERENCE.value,
        title="the user distinguished value 112,000 USD",
        content="the user",
    )
    repo = FakeMemoryRepository(records=[existing])
    versions = RecordingVersions()
    deduplicator = MemoryDeduplicator(repo, FixedSimilarity(0.88), version_repository=versions)

    result = await deduplicator.deduplicate(payload, incoming("the user"))

    assert result.action == "store"
    assert versions.created == []

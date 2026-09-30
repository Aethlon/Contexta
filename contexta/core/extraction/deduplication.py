"""Memory deduplication for extracted memory candidates."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Protocol

from contexta.core.schemas import ExtractedMemory, ObservationPayload
from contexta.core.truth.service import fact_value
from contexta.core.types import MemoryType
from contexta.models.version import MemoryVersion


class DeduplicationRepository(Protocol):
    """Repository methods required by the deduplication engine."""

    async def get_by_type(
        self,
        user_id: uuid.UUID,
        memory_type: MemoryType,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[object]:
        """Return scoped candidate memories for a user and type."""
        ...

    async def update_by_id(
        self,
        record_id: uuid.UUID,
        values: dict,
    ) -> int:
        """Update an existing memory record."""
        ...


class VersionWriterProtocol(Protocol):
    """Version sink used to preserve a record before it is overwritten."""

    async def create(self, record: MemoryVersion) -> MemoryVersion:
        ...


class SimilarityProvider(Protocol):
    """Optional semantic similarity provider."""

    async def similarity(self, left: str, right: str) -> float:
        """Return semantic similarity in [0.0, 1.0]."""
        ...


@dataclass(frozen=True)
class DeduplicationResult:
    """Result of applying deduplication to a memory candidate."""

    action: str
    memory: ExtractedMemory | None = None
    existing_id: uuid.UUID | None = None
    similarity: float = 0.0


class SequenceMatcherSimilarity:
    """Local fallback similarity provider for deterministic behavior."""

    async def similarity(self, left: str, right: str) -> float:
        return SequenceMatcher(None, left.lower(), right.lower()).ratio()


class MemoryDeduplicator:
    """Apply duplicate discard and near-duplicate merge thresholds."""

    DUPLICATE_THRESHOLD = 0.95
    MERGE_THRESHOLD = 0.85

    def __init__(
        self,
        repository: DeduplicationRepository,
        similarity_provider: SimilarityProvider | None = None,
        *,
        version_repository: VersionWriterProtocol | None = None,
    ) -> None:
        self._repository = repository
        self._similarity = similarity_provider or SequenceMatcherSimilarity()
        self._versions = version_repository

    async def deduplicate(
        self,
        payload: ObservationPayload,
        memory: ExtractedMemory,
        *,
        fact_key: str | None = None,
    ) -> DeduplicationResult:
        """Deduplicate a memory against same-user, same-tenant, same-type records."""
        now = datetime.now(UTC).replace(tzinfo=None)

        if fact_key is not None:
            incumbent = await self._slot_incumbent(payload, memory, fact_key)
            if incumbent is not None:
                return await self._deduplicate_within_slot(incumbent, memory, now)

        candidates = await self._repository.get_by_type(
            payload.user_id,
            memory.memory_type,
            limit=100,
        )
        # A repository that does not filter cannot be trusted to hand back only
        # current rows, and merging into a superseded one hides the new evidence
        # from every read.
        candidates = [
            candidate
            for candidate in candidates
            if getattr(candidate, "valid_to", None) is None
        ]
        best_candidate, best_similarity = await self._find_best_match(
            memory,
            candidates,
        )

        if best_candidate is None:
            return DeduplicationResult(action="store", memory=memory)

        existing_id = best_candidate.id

        if best_similarity > self.DUPLICATE_THRESHOLD:
            await self._repository.update_by_id(existing_id, {"updated_at": now})
            return DeduplicationResult(
                action="discard",
                existing_id=existing_id,
                similarity=best_similarity,
            )

        if best_similarity >= self.MERGE_THRESHOLD:
            merged_values = self._merge_values(best_candidate, memory, now)
            if merged_values is None:
                # A merge that would not grow the existing content is not a
                # merge. Reporting one made the caller drop the incoming memory
                # as "already merged" while nothing was actually merged, which
                # silently lost an observation. Store it separately instead: a
                # redundant row is recoverable, a lost one is not.
                return DeduplicationResult(
                    action="store",
                    memory=memory,
                    similarity=best_similarity,
                )
            await self._snapshot_pre_merge(best_candidate, now)
            await self._repository.update_by_id(existing_id, merged_values)
            return DeduplicationResult(
                action="merge",
                existing_id=existing_id,
                similarity=best_similarity,
            )

        return DeduplicationResult(action="store", memory=memory, similarity=best_similarity)

    async def _slot_incumbent(
        self,
        payload: ObservationPayload,
        memory: ExtractedMemory,
        fact_key: str,
    ) -> object | None:
        """The current row already holding this fact slot, if it can be asked.

        A slot lookup, not a scan of the type window: the window is bounded and
        the incumbent is older than the incoming memory, so it is exactly the row
        such a window drops first.
        """
        query = getattr(self._repository, "get_current_by_fact_key", None)
        if query is None:
            return None
        rows = await query(fact_key, user_id=payload.user_id, memory_type=memory.memory_type)
        for row in rows:
            if getattr(row, "valid_to", None) is None:
                return row
        return None

    async def _deduplicate_within_slot(
        self,
        incumbent: object,
        memory: ExtractedMemory,
        now: datetime,
    ) -> DeduplicationResult:
        """Decide a memory whose fact slot is already occupied.

        The slot outranks the text. Character similarity would keep the older
        value current for a high-overlap edit ("My salary is 100k." against
        "My salary is 120k." scores above the duplicate threshold), which is
        exactly the stale-truth failure this slot exists to prevent, and one slot
        may only have one current row. So the same assertion is discarded here
        rather than stored as a second current row, and a different one is stored
        for truth maintenance to supersede the incumbent with.
        """
        if fact_value(incumbent) == fact_value(memory):
            await self._repository.update_by_id(incumbent.id, {"updated_at": now})
            return DeduplicationResult(
                action="discard",
                existing_id=incumbent.id,
                similarity=1.0,
            )
        return DeduplicationResult(action="store", memory=memory)

    async def _snapshot_pre_merge(self, existing: object, merged_at: datetime) -> None:
        """Preserve the pre-merge state of a record that is about to be rewritten.

        A merge overwrites title, content and structured_data in place, so
        without a `MemoryVersion` the previous wording is unrecoverable and the
        change is invisible to truth maintenance, which reads lineage from
        versions. `superseded_by_id` stays null: the record continues, it is not
        replaced.
        """
        if self._versions is None:
            return
        valid_from = getattr(existing, "valid_from", None)
        await self._versions.create(
            MemoryVersion(
                memory_id=existing.id,
                superseded_by_id=None,
                content=str(getattr(existing, "content", "") or ""),
                structured_data=getattr(existing, "structured_data", None),
                importance=float(getattr(existing, "importance", 0.0) or 0.0),
                valid_from=valid_from if valid_from is not None else merged_at,
                valid_to=merged_at,
            )
        )

    async def _find_best_match(
        self,
        memory: ExtractedMemory,
        candidates: Sequence[object],
    ) -> tuple[object | None, float]:
        best_candidate: object | None = None
        best_similarity = 0.0
        incoming_text = self._comparison_text(memory.title, memory.content)

        for candidate in candidates:
            candidate_text = self._comparison_text(
                str(getattr(candidate, "title", "")),
                str(getattr(candidate, "content", "")),
            )
            score = await self._similarity.similarity(incoming_text, candidate_text)
            if score > best_similarity:
                best_candidate = candidate
                best_similarity = score

        return best_candidate, best_similarity

    def _comparison_text(self, title: str, content: str) -> str:
        return f"{title.strip()}\n{content.strip()}".strip()

    def _merge_values(
        self,
        existing: object,
        incoming: ExtractedMemory,
        updated_at: datetime,
    ) -> dict | None:
        """Build the merged row, or None when a merge would add nothing.

        Returns None rather than a dict whenever the merge cannot strictly grow
        the existing content -- when the incoming text is empty, or is already a
        substring of it. Both are common once degenerate short bodies reach the
        store: with ``existing.content == "the user"`` and an incoming body that
        is also short, the substring test succeeds, the concatenation is skipped,
        and the caller is handed an unchanged row while still being told
        ``"merge"``. The caller skips storing on ``"merge"``, so the new memory
        was never written anywhere. Merging must incorporate new evidence or it
        must not be claimed.
        """
        existing_content = str(getattr(existing, "content", "")).strip()
        incoming_content = incoming.content.strip()
        if incoming_content and incoming_content not in existing_content:
            content = f"{existing_content}\n\n{incoming_content}".strip()
        else:
            content = existing_content
        if len(content) <= len(existing_content):
            return None

        existing_tags = list(getattr(existing, "tags", None) or [])
        tags = list(dict.fromkeys([*existing_tags, *incoming.tags]))

        structured_data = getattr(existing, "structured_data", None)
        if isinstance(structured_data, dict) and isinstance(incoming.structured_data, dict):
            structured_data = {**structured_data, **incoming.structured_data}
        elif structured_data is None:
            structured_data = incoming.structured_data

        return {
            "title": str(getattr(existing, "title", "")) or incoming.title,
            "content": content,
            "search_text": " ".join(
                part
                for part in (
                    str(getattr(existing, "title", "")) or incoming.title,
                    content,
                    " ".join(tags),
                )
                if part
            ),
            "structured_data": structured_data,
            "tags": tags,
            "updated_at": updated_at,
        }

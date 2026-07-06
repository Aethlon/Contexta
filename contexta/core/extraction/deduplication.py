"""Memory deduplication for extracted memory candidates."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Protocol, Sequence

from contexta.core.schemas import ExtractedMemory, ObservationPayload
from contexta.core.types import MemoryType


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
    ) -> None:
        self._repository = repository
        self._similarity = similarity_provider or SequenceMatcherSimilarity()

    async def deduplicate(
        self,
        payload: ObservationPayload,
        memory: ExtractedMemory,
    ) -> DeduplicationResult:
        """Deduplicate a memory against same-user, same-tenant, same-type records."""
        candidates = await self._repository.get_by_type(
            payload.user_id,
            memory.memory_type,
            limit=100,
        )
        best_candidate, best_similarity = await self._find_best_match(
            memory,
            candidates,
        )

        if best_candidate is None:
            return DeduplicationResult(action="store", memory=memory)

        existing_id = getattr(best_candidate, "id")
        now = datetime.utcnow()

        if best_similarity > self.DUPLICATE_THRESHOLD:
            await self._repository.update_by_id(existing_id, {"updated_at": now})
            return DeduplicationResult(
                action="discard",
                existing_id=existing_id,
                similarity=best_similarity,
            )

        if best_similarity >= self.MERGE_THRESHOLD:
            merged_values = self._merge_values(best_candidate, memory, now)
            await self._repository.update_by_id(existing_id, merged_values)
            return DeduplicationResult(
                action="merge",
                existing_id=existing_id,
                similarity=best_similarity,
            )

        return DeduplicationResult(action="store", memory=memory, similarity=best_similarity)

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
    ) -> dict:
        existing_content = str(getattr(existing, "content", "")).strip()
        incoming_content = incoming.content.strip()
        if incoming_content and incoming_content not in existing_content:
            content = f"{existing_content}\n\n{incoming_content}".strip()
        else:
            content = existing_content

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
            "structured_data": structured_data,
            "tags": tags,
            "updated_at": updated_at,
        }

"""Retrieval feedback tracking and utility adjustment."""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Protocol, Sequence

from contexta.core.types import UsageSignal
from contexta.models.feedback import RetrievalFeedback


class FeedbackRepository(Protocol):
    async def create(self, record: RetrievalFeedback) -> RetrievalFeedback:
        ...

    async def get_by_target(self, target_id: uuid.UUID, *, offset: int = 0, limit: int = 100) -> Sequence[RetrievalFeedback]:
        ...


@dataclass(frozen=True)
class FeedbackCounts:
    retrieval_count: int
    used_count: int
    ignored_count: int


class RetrievalFeedbackEngine:
    """Record retrieval and usage signals for utility scoring."""

    def __init__(self, repository: FeedbackRepository | None = None) -> None:
        self._repository = repository
        self._events: dict[uuid.UUID, list[RetrievalFeedback]] = {}

    async def record_retrieval(
        self,
        *,
        memory_ids: Sequence[uuid.UUID],
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None = None,
        context_request_id: uuid.UUID | None = None,
    ) -> list[RetrievalFeedback]:
        return [
            await self._record(
                memory_id=memory_id,
                organization_id=organization_id,
                user_id=user_id,
                signal="retrieved",
                session_id=session_id,
                context_request_id=context_request_id,
            )
            for memory_id in memory_ids
        ]

    async def record_usage(
        self,
        *,
        memory_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        signal: UsageSignal,
        session_id: uuid.UUID | None = None,
        context_request_id: uuid.UUID | None = None,
    ) -> RetrievalFeedback:
        return await self._record(
            memory_id=memory_id,
            organization_id=organization_id,
            user_id=user_id,
            signal=signal.value,
            session_id=session_id,
            context_request_id=context_request_id,
        )

    def compute_utility_ratio(self, used_count: int, retrieval_count: int) -> float:
        if retrieval_count <= 0:
            return 0.0
        return max(0.0, min(1.0, used_count / retrieval_count))

    def apply_importance_adjustment(
        self,
        *,
        current_importance: float,
        retrieval_count: int,
        used_count: int,
        ignored_count: int,
    ) -> float:
        if ignored_count >= 10 and used_count == 0:
            return max(0.0, current_importance - 0.1)
        if retrieval_count >= 10 and self.compute_utility_ratio(used_count, retrieval_count) > 0.8:
            return min(1.0, current_importance + 0.05)
        return current_importance

    def counts_for(self, memory_id: uuid.UUID) -> FeedbackCounts:
        counter = Counter(event.signal for event in self._events.get(memory_id, []))
        return FeedbackCounts(
            retrieval_count=counter["retrieved"],
            used_count=counter[UsageSignal.USED.value],
            ignored_count=counter[UsageSignal.IGNORED.value],
        )

    async def _record(
        self,
        *,
        memory_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        signal: str,
        session_id: uuid.UUID | None,
        context_request_id: uuid.UUID | None,
    ) -> RetrievalFeedback:
        feedback = RetrievalFeedback(
            memory_id=memory_id,
            organization_id=organization_id,
            user_id=user_id,
            session_id=session_id,
            context_request_id=context_request_id,
            signal=signal,
        )
        self._events.setdefault(memory_id, []).append(feedback)
        if self._repository is not None:
            await self._repository.create(feedback)
        return feedback

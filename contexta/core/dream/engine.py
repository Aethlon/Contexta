"""Dream cycle engine."""

from __future__ import annotations

import uuid

from contexta.models.dream import MissingMemoryCandidate


class DreamCycleEngine:
    """Evaluate synthetic questions and record knowledge gaps."""

    def generate_questions(self, entities: list) -> list[tuple[str, uuid.UUID | None]]:
        questions = []
        for entity in entities:
            questions.append((f"What do we know about {entity.name}?", entity.id))
        return questions

    def identify_gap(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        question: str,
        related_entity_id: uuid.UUID | None,
        confidence: float,
    ) -> MissingMemoryCandidate | None:
        if confidence >= 0.5:
            return None
        return MissingMemoryCandidate(
            organization_id=organization_id,
            user_id=user_id,
            question=question,
            related_entity_id=related_entity_id,
            status="open",
        )

    def utility_delta(self, *, confidence: float) -> float:
        return 0.05 if confidence >= 0.5 else -0.05

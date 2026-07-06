"""Memory compression engine."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from contexta.models.compression import CompressedSummary


class MemoryCompressionEngine:
    """Generate compact entity summaries for large memory sets."""

    MIN_SOURCE_MEMORIES = 20

    def should_compress(self, memories: list) -> bool:
        return len(memories) >= self.MIN_SOURCE_MEMORIES

    def generate_summary(self, *, entity_id: uuid.UUID, organization_id: uuid.UUID, memories: list) -> CompressedSummary | None:
        if not self.should_compress(memories):
            return None
        combined = " ".join(memory.content for memory in memories)
        summary_text = combined[: max(1, int(len(combined) * 0.4))]
        return CompressedSummary(
            entity_id=entity_id,
            organization_id=organization_id,
            summary_text=summary_text,
            key_facts={"facts": [memory.title for memory in memories[:10]]},
            confidence=0.7,
            source_memory_count=len(memories),
            is_stale=False,
            generated_at=datetime.now(timezone.utc),
        )

    def mark_stale(self, summary: CompressedSummary) -> CompressedSummary:
        summary.is_stale = True
        return summary

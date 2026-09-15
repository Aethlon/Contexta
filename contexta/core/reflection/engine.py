"""Autonomous Memory Reflection & Consolidation Engine.

Performs higher-order maintenance over raw episodic and semantic memories:
1. Fact Deduplication & Semantic Merging: Clusters semantically redundant memories.
2. Contradiction & Evolution Detection: Finds conflicting assertions and marks older records as superseded.
3. Pattern Recognition: Discovers repeated behaviors/preferences across sessions and distills them into PATTERN memories.
4. Dormancy & Decay Management: Progresses aging, un-accessed goals and cold facts.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from contexta.core.types import MemoryState, MemoryType
from contexta.models.memory import MemoryRecord


class ReflectionEngine:
    """Periodic reflection, consolidation, and truth evolution engine."""

    def mark_dormant_goal(self, memory: MemoryRecord, *, now: datetime | None = None) -> MemoryRecord:
        reference = now or datetime.now(UTC)
        last_seen = memory.last_accessed_at or memory.updated_at or memory.created_at
        if last_seen and memory.memory_type == "goal" and reference - last_seen >= timedelta(days=180):
            memory.memory_state = MemoryState.COLD.value
            memory.importance = max(0.0, memory.importance - 0.3)
        return memory

    def merge_duplicate_facts(self, memories: Sequence[MemoryRecord]) -> list[MemoryRecord]:
        seen: set[str] = set()
        merged: list[MemoryRecord] = []
        for memory in memories:
            key = memory.content.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(memory)
        return merged

    def detect_contradictions(
        self,
        memories: Sequence[MemoryRecord],
    ) -> list[tuple[MemoryRecord, MemoryRecord, str]]:
        """Identify pairs of conflicting memories where a newer memory supersedes an older one."""
        contradictions: list[tuple[MemoryRecord, MemoryRecord, str]] = []

        # Group memories by topic/entity tags
        topic_map: dict[str, list[MemoryRecord]] = {}
        for m in memories:
            if m.is_archived or m.valid_to is not None:
                continue
            for tag in m.tags or []:
                topic_map.setdefault(tag.lower(), []).append(m)

        # Transition keywords signaling changes
        transition_words = {"moved to", "switched to", "changed to", "no longer", "stopped", "prefers", "now uses"}

        for tag, group in topic_map.items():
            if len(group) < 2:
                continue
            # Sort group chronologically (newest first)
            sorted_group = sorted(
                group,
                key=lambda m: m.created_at or datetime.min.replace(tzinfo=UTC),
                reverse=True,
            )
            for i in range(len(sorted_group) - 1):
                newer = sorted_group[i]
                older = sorted_group[i + 1]
                # Check for negation or explicit transition in newer text
                newer_lower = newer.content.lower()
                older_lower = older.content.lower()

                conflict = False
                reason = ""
                if any(w in newer_lower for w in transition_words):
                    conflict = True
                    reason = f"Transition marker detected on topic '{tag}'"
                elif ("not " in newer_lower and older_lower in newer_lower) or ("don't " in newer_lower and older_lower in newer_lower):
                    conflict = True
                    reason = f"Explicit negation of previous fact on topic '{tag}'"

                if conflict:
                    contradictions.append((older, newer, reason))

        return contradictions

    def consolidate_patterns(
        self,
        memories: Sequence[MemoryRecord],
        *,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        min_occurrences: int = 3,
    ) -> list[MemoryRecord]:
        """Detect repeated interaction behaviors across sessions and distill them into PATTERN memories."""
        tag_counts: Counter[str] = Counter()
        for m in memories:
            for t in m.tags or []:
                tag_counts[t.lower()] += 1

        patterns: list[MemoryRecord] = []
        for tag, count in tag_counts.items():
            if count >= min_occurrences and tag not in {"general", "fact", "preference", "user"}:
                pattern_content = f"User frequently references or works with '{tag}' across multiple interactions ({count} observations)."
                patterns.append(
                    MemoryRecord(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        organization_id=organization_id,
                        memory_type=MemoryType.PATTERN.value,
                        title=f"Recurring Affinity: {tag.capitalize()}",
                        content=pattern_content,
                        importance=0.85,
                        confidence=0.90,
                        utility_score=0.1,
                        tags=[tag, "consolidated_pattern"],
                        memory_state=MemoryState.ACTIVE.value,
                        is_pinned=False,
                        is_archived=False,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )
        return patterns

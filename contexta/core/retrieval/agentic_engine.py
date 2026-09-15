"""Agentic Investigative Retrieval Engine (ASMR-style / Multi-Agent Reasoning over Memory).

Instead of a passive single-pass vector/keyword search, the AgenticRetrievalEngine
investigates the memory network iteratively:
1. Intent & Entity Decomposition: Extracts inquiry targets, temporal keywords, and relation predicates.
2. Seed Retrieval: Fast initial hybrid retrieval.
3. Graph & Knowledge Gap Analysis: Discovers referenced entities and checks for predecessor/successor relations (SUPERSEDED_BY, DEPENDS_ON, USES).
4. Iterative Sub-Investigations: Issues focused follow-up queries along graph edges if initial evidence is incomplete.
5. Temporal Evolution & Contradiction Resolution: Traces fact changes over time and synthesizes a structured investigation trace.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Sequence

from contexta.core.retrieval.engine import RetrievalEngine, RetrievalResult
from contexta.core.schemas import RetrievalQuery
from contexta.models.entity import Entity, EntityEdge
from contexta.models.memory import MemoryRecord

logger = logging.getLogger(__name__)


@dataclass
class InvestigationStep:
    step_number: int
    action: str
    target: str
    discovered_count: int
    rationale: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class InvestigativeResult:
    query: str
    user_id: uuid.UUID
    memories: list[RetrievalResult]
    investigation_trace: list[InvestigationStep]
    entities_discovered: list[str]
    temporal_evolution: list[dict[str, Any]]
    synthesized_context: str
    execution_time_ms: float = 0.0


class AgenticRetrievalEngine:
    """Iteratively investigates memory graphs to answer complex multi-hop queries."""

    TEMPORAL_MARKERS = {
        "before", "previously", "prior", "earlier", "switched", "migrated",
        "originally", "formerly", "used to", "history", "timeline", "past",
        "superseded", "replaced", "after", "now", "current", "latest",
    }

    CAUSAL_MARKERS = {
        "why", "reason", "cause", "led to", "because", "due to", "trigger",
        "dependency", "blocked by", "resulted in",
    }

    def __init__(
        self,
        retrieval_engine: RetrievalEngine,
        entity_repository: Any = None,
        edge_repository: Any = None,
    ) -> None:
        self._retrieval_engine = retrieval_engine
        self._entities = entity_repository
        self._edges = edge_repository

    async def investigate(
        self,
        *,
        query_text: str,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        max_hops: int = 2,
        limit: int = 15,
        query_embedding: list[float] | None = None,
    ) -> InvestigativeResult:
        start_time = datetime.now(UTC)
        trace: list[InvestigationStep] = []
        collected_memories: dict[uuid.UUID, RetrievalResult] = {}
        all_discovered_entities: set[str] = set()
        temporal_events: list[dict[str, Any]] = []

        # 1. Intent & Temporal Decomposition (substring match: multi-word
        # markers like "used to" / "blocked by" never survive .split()).
        q_lower = query_text.lower()
        is_temporal = any(marker in q_lower for marker in self.TEMPORAL_MARKERS)
        is_causal = any(marker in q_lower for marker in self.CAUSAL_MARKERS)

        trace.append(
            InvestigationStep(
                step_number=1,
                action="decompose_intent",
                target=query_text,
                discovered_count=0,
                rationale=f"Classified query intent: temporal={is_temporal}, causal={is_causal}",
                details={"temporal": is_temporal, "causal": is_causal},
            )
        )

        # 2. Seed Retrieval
        seed_query = RetrievalQuery(
            query_text=query_text,
            user_id=user_id,
            organization_id=organization_id,
            limit=limit,
            graph_depth=1,
            include_cold=is_temporal,  # Include historical cold memories for temporal queries
        )
        seed_results = await self._retrieval_engine.retrieve(seed_query, query_embedding=query_embedding)
        for r in seed_results:
            collected_memories[r.memory.id] = r
            if r.memory.tags:
                all_discovered_entities.update(r.memory.tags)

        trace.append(
            InvestigationStep(
                step_number=2,
                action="seed_retrieval",
                target=query_text,
                discovered_count=len(seed_results),
                rationale=f"Retrieved {len(seed_results)} primary seed memories using hybrid scoring",
                details={"memory_ids": [str(r.memory.id) for r in seed_results[:5]]},
            )
        )

        # 3. Graph Gap & Entity Follow-Up (Hop 1..max_hops)
        current_hop = 1
        while current_hop <= max_hops:
            # Detect entities mentioned in seed memories that warrant follow-up
            referenced_entities = self._extract_candidate_entities(collected_memories.values())
            unexplored = referenced_entities - all_discovered_entities

            if not unexplored:
                # If no new entities to explore, check superseded / historical chain.
                superseded_ids = [
                    r.memory.id for r in collected_memories.values()
                    if getattr(r.memory, "supersedes_id", None) or r.memory.valid_to
                ]
                if superseded_ids and is_temporal:
                    trace.append(
                        InvestigationStep(
                            step_number=len(trace) + 1,
                            action="trace_evolution",
                            target="superseded_memories",
                            discovered_count=len(superseded_ids),
                            rationale="Identified superseded facts in knowledge evolution chain",
                            details={"superseded_count": len(superseded_ids)},
                        )
                    )
                break

            # Pick candidate entity with the most score-weighted evidence
            # (not alphabetical) to follow the strongest lead first.
            focus_entity = self._top_entity(collected_memories.values(), unexplored)
            all_discovered_entities.add(focus_entity)

            # Targeted sub-investigation (keeps vector signal for hybrid scoring)
            sub_query_text = f"{focus_entity} history context" if is_temporal else f"{focus_entity} details {query_text}"
            sub_query = RetrievalQuery(
                query_text=sub_query_text,
                user_id=user_id,
                organization_id=organization_id,
                limit=5,
                include_cold=is_temporal,
            )
            sub_results = await self._retrieval_engine.retrieve(sub_query, query_embedding=query_embedding)
            new_finds = 0
            for r in sub_results:
                if r.memory.id not in collected_memories:
                    collected_memories[r.memory.id] = r
                    new_finds += 1

            trace.append(
                InvestigationStep(
                    step_number=len(trace) + 1,
                    action="investigate_subgraph",
                    target=focus_entity,
                    discovered_count=new_finds,
                    rationale=f"Followed entity edge '{focus_entity}' to uncover secondary evidence",
                    details={"entity": focus_entity, "new_memories": new_finds},
                )
            )

            current_hop += 1

        # 4. Temporal Sorting & Evolution Assembly
        sorted_results = sorted(
            collected_memories.values(),
            key=lambda r: (r.score + (0.1 if not r.memory.valid_to else -0.1)),
            reverse=True,
        )[:limit]

        # Extract temporal timeline
        for r in sorted_results:
            if r.memory.created_at:
                temporal_events.append({
                    "timestamp": r.memory.created_at.isoformat(),
                    "title": r.memory.title,
                    "content": r.memory.content,
                    "is_current": r.memory.valid_to is None,
                    "memory_type": r.memory.memory_type,
                })
        temporal_events.sort(key=lambda e: e["timestamp"])

        # 5. Synthesize XML Structured Context
        synthesized_context = self._format_investigative_context(
            query=query_text,
            trace=trace,
            memories=sorted_results,
            timeline=temporal_events,
        )

        duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000.0

        return InvestigativeResult(
            query=query_text,
            user_id=user_id,
            memories=sorted_results,
            investigation_trace=trace,
            entities_discovered=sorted(all_discovered_entities),
            temporal_evolution=temporal_events,
            synthesized_context=synthesized_context,
            execution_time_ms=round(duration_ms, 2),
        )

    def _top_entity(self, results: Sequence[RetrievalResult], candidates: set[str]) -> str:
        """Score candidate entities by score-weighted mention count."""
        weights: dict[str, float] = {c: 0.0 for c in candidates}
        for r in results:
            w = max(0.0, r.score)
            for ent in self._entities_in_result(r):
                if ent in weights:
                    weights[ent] += w
        best = max(weights.items(), key=lambda item: (item[1], item[0]))
        return best[0]

    def _entities_in_result(self, r: RetrievalResult) -> set[str]:
        found: set[str] = set()
        if r.memory.tags:
            found.update([t.lower() for t in r.memory.tags if len(t) > 2])
        for pn in re.findall(r"\b[A-Z][a-zA-Z0-9_-]{2,}\b", r.memory.content or ""):
            if pn.lower() not in {"the", "and", "this", "that", "with", "from", "user", "assistant"}:
                found.add(pn.lower())
        return found

    def _extract_candidate_entities(self, results: Sequence[RetrievalResult]) -> set[str]:
        candidates: set[str] = set()
        for r in results:
            if r.memory.tags:
                candidates.update([t.lower() for t in r.memory.tags if len(t) > 2])
            # Match capitalized Proper Nouns from content
            proper_nouns = re.findall(r"\b[A-Z][a-zA-Z0-9_-]{2,}\b", r.memory.content)
            for pn in proper_nouns:
                if pn.lower() not in {"the", "and", "this", "that", "with", "from", "user", "assistant"}:
                    candidates.add(pn.lower())
        return candidates

    def _format_investigative_context(
        self,
        *,
        query: str,
        trace: list[InvestigationStep],
        memories: list[RetrievalResult],
        timeline: list[dict[str, Any]],
    ) -> str:
        parts: list[str] = []
        parts.append(f"<memory_investigation query=\"{query}\">")

        parts.append("  <investigation_trace>")
        for step in trace:
            parts.append(f"    <step n=\"{step.step_number}\" action=\"{step.action}\" target=\"{step.target}\">")
            parts.append(f"      <rationale>{step.rationale}</rationale>")
            parts.append("    </step>")
        parts.append("  </investigation_trace>")

        if timeline:
            parts.append("  <temporal_evolution>")
            for evt in timeline:
                status = "CURRENT" if evt["is_current"] else "SUPERSEDED_OR_HISTORICAL"
                parts.append(f"    <event time=\"{evt['timestamp']}\" status=\"{status}\">")
                parts.append(f"      <title>{evt['title']}</title>")
                parts.append(f"      <fact>{evt['content']}</fact>")
                parts.append("    </event>")
            parts.append("  </temporal_evolution>")

        parts.append("  <verified_evidence>")
        for idx, r in enumerate(memories, 1):
            parts.append(f"    <evidence id=\"{r.memory.id}\" rank=\"{idx}\" confidence=\"{r.score:.3f}\" type=\"{r.memory.memory_type}\">")
            parts.append(f"      <title>{r.memory.title}</title>")
            parts.append(f"      <content>{r.memory.content}</content>")
            parts.append("    </evidence>")
        parts.append("  </verified_evidence>")

        parts.append("</memory_investigation>")
        return "\n".join(parts)

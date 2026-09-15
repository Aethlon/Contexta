"""High-speed extraction-to-graph pipeline orchestrator.

Orchestrates memory ingestion, deduplication, in-memory bulk entity resolution,
graph construction, and atomic persistence in cleanly staged, millisecond-timed phases.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from contexta.core.entities.bulk_resolver import BulkEntityResolver, BulkResolutionResult
from contexta.core.extraction.deduplication import MemoryDeduplicator
from contexta.core.extraction.worker import ExtractionWorker
from contexta.core.graph.cache import GraphCache
from contexta.core.schemas import ExtractedMemory, ImportanceSignals, ObservationPayload
from contexta.core.scoring.engine import MemoryScoringEngine
from contexta.core.truth.maintenance import TruthMaintenanceEngine
from contexta.core.types import MemoryState
from contexta.models.memory import MemoryRecord
from contexta.repositories.audit_repo import AuditRepository
from contexta.repositories.entity_repo import (
    EntityEdgeRepository,
    EntityRepository,
    MemoryEntityLinkRepository,
)
from contexta.repositories.memory_repo import MemoryRepository
from contexta.repositories.version_repo import MemoryVersionRepository
from contexta.workers.embedding_tasks import enqueue_embedding_generation

logger = logging.getLogger(__name__)


@dataclass
class StageTimings:
    """Millisecond execution latency across orchestrated pipeline stages."""

    extraction_ms: float = 0.0
    deduplication_ms: float = 0.0
    entity_graph_ms: float = 0.0
    persistence_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class OrchestrationResult:
    """Comprehensive result of orchestrated memory processing."""

    extracted_count: int = 0
    stored_count: int = 0
    merged_count: int = 0
    discarded_count: int = 0
    new_entities_count: int = 0
    new_edges_count: int = 0
    new_links_count: int = 0
    timings: StageTimings = field(default_factory=StageTimings)
    details: list[dict[str, Any]] = field(default_factory=list)


class FastMemoryOrchestrator:
    """High-throughput, millisecond-orchestrated memory and graph pipeline."""

    def __init__(
        self,
        *,
        extraction_worker: ExtractionWorker | None = None,
        scoring_engine: MemoryScoringEngine | None = None,
        graph_cache: GraphCache | None = None,
    ) -> None:
        self._extractor = extraction_worker or ExtractionWorker()
        self._scoring = scoring_engine or MemoryScoringEngine()
        self._graph_cache = graph_cache or GraphCache()

    async def orchestrate(
        self,
        payload: ObservationPayload,
        session: AsyncSession,
    ) -> OrchestrationResult:
        """Run observation through the high-speed staged pipeline."""
        t_start = time.perf_counter()
        org_id = payload.organization_id
        user_id = payload.user_id
        session_id = payload.session_id
        now_ts = datetime.now(UTC).replace(tzinfo=None)

        result = OrchestrationResult()
        timings = StageTimings()

        # ── STAGE 1 & 2: EXTRACTION & SCORING ────────────────────────────
        t0 = time.perf_counter()
        extracted = await self._extractor.extract(payload)
        timings.extraction_ms = round((time.perf_counter() - t0) * 1000, 2)
        result.extracted_count = len(extracted)

        if not extracted:
            timings.total_ms = round((time.perf_counter() - t_start) * 1000, 2)
            result.timings = timings
            return result

        # ── STAGE 3: REPOSITORIES & DEDUPLICATION ────────────────────────
        t1 = time.perf_counter()
        memory_repo = MemoryRepository(session, tenant_id=org_id)
        entity_repo = EntityRepository(session, tenant_id=org_id)
        link_repo = MemoryEntityLinkRepository(session, tenant_id=org_id)
        edge_repo = EntityEdgeRepository(session, tenant_id=org_id)
        version_repo = MemoryVersionRepository(session)
        audit_repo = AuditRepository(session, tenant_id=org_id)

        deduplicator = MemoryDeduplicator(memory_repo)
        truth_engine = TruthMaintenanceEngine(
            memory_repo,
            version_repo,
            edge_repository=edge_repo,
            audit_repository=audit_repo,
        )

        valid_memories: list[tuple[ExtractedMemory, float, float]] = []
        for mem in extracted:
            dedup = await deduplicator.deduplicate(payload, mem)
            if dedup.action == "discard":
                result.discarded_count += 1
                result.details.append({"title": mem.title, "action": "discard", "existing_id": str(dedup.existing_id)})
                continue
            if dedup.action == "merge":
                result.merged_count += 1
                result.details.append({"title": mem.title, "action": "merge", "existing_id": str(dedup.existing_id)})
                enqueue_embedding_generation(str(dedup.existing_id))
                continue

            # Compute scores with real per-memory signals (entity mentions,
            # emphasis and decision impact come straight from extraction).
            signals = ImportanceSignals(
                mention_count=len(mem.entities),
                has_emphasis=mem.has_emphasis,
                impacts_decisions=mem.impacts_decisions,
            )
            score = self._scoring.compute_importance(mem.memory_type, mem.content, signals)
            conf = self._scoring.compute_confidence(mem.source_type)
            valid_memories.append((mem, score.final_score, conf))

        timings.deduplication_ms = round((time.perf_counter() - t1) * 1000, 2)

        if not valid_memories:
            timings.total_ms = round((time.perf_counter() - t_start) * 1000, 2)
            result.timings = timings
            return result

        # ── STAGE 4: IN-MEMORY BULK ENTITY RESOLUTION & GRAPH BUILDING ────
        t2 = time.perf_counter()
        # Instantiate memory records with deterministic IDs
        mem_records_to_add: list[MemoryRecord] = []
        mem_pairs: list[tuple[uuid.UUID, ExtractedMemory]] = []

        for mem, imp, conf in valid_memories:
            rec_id = uuid.uuid4()
            m_type = mem.memory_type.value if hasattr(mem.memory_type, "value") else str(mem.memory_type)
            s_type = mem.source_type.value if hasattr(mem.source_type, "value") else str(mem.source_type)
            record = MemoryRecord(
                id=rec_id,
                user_id=user_id,
                organization_id=org_id,
                session_id=session_id,
                memory_type=m_type,
                title=mem.title,
                content=mem.content,
                structured_data=mem.structured_data,
                source_type=s_type,
                confidence=conf,
                importance=imp,
                utility_score=0.0,
                tags=mem.tags,
                memory_state=MemoryState.ACTIVE.value,
                is_pinned=False,
                is_archived=False,
                valid_from=now_ts,
                valid_to=None,
                embedding=getattr(mem, "embedding", None),
            )
            mem_records_to_add.append(record)
            mem_pairs.append((rec_id, mem))

        bulk_resolver = BulkEntityResolver(entity_repo, link_repo, edge_repo)
        graph_res: BulkResolutionResult = await bulk_resolver.resolve_batch(
            user_id=user_id,
            organization_id=org_id,
            memories=mem_pairs,
            observed_at=now_ts,
        )
        timings.entity_graph_ms = round((time.perf_counter() - t2) * 1000, 2)

        # ── STAGE 5: ATOMIC PERSISTENCE & TRUTH APPLICATION ──────────────
        t3 = time.perf_counter()
        # 1. Add all memory records
        session.add_all(mem_records_to_add)

        # 2. Add all new entity records
        if graph_res.new_entities:
            session.add_all(graph_res.new_entities)

        # 2b. Persist mention-count / timestamp updates for matched entities
        # (previously collected but silently dropped).
        for entity_id, values in graph_res.updated_entities:
            await entity_repo.update_by_id(entity_id, values)

        # 3. Add all links and edges
        if graph_res.links:
            session.add_all(graph_res.links)
        if graph_res.edges:
            session.add_all(graph_res.edges)

        # Flush to DB in a single roundtrip
        await session.flush()

        # Apply truth maintenance / supersession in-memory
        for rec in mem_records_to_add:
            ent_list = graph_res.memory_to_entities.get(rec.id, [])
            ent_ids = [e.id for e in ent_list]
            await truth_engine.apply(rec, entity_ids=ent_ids, actor_id=user_id)
            enqueue_embedding_generation(str(rec.id))
            result.details.append({
                "title": rec.title,
                "action": "store",
                "memory_id": str(rec.id),
                "importance": rec.importance,
                "entities": [e.name for e in ent_list],
            })

        # Update Redis Graph Cache with new edges in background
        if graph_res.edges:
            self._graph_cache.update_edges(user_id, graph_res.edges)

        timings.persistence_ms = round((time.perf_counter() - t3) * 1000, 2)
        timings.total_ms = round((time.perf_counter() - t_start) * 1000, 2)

        result.stored_count = len(mem_records_to_add)
        result.new_entities_count = len(graph_res.new_entities)
        result.new_edges_count = len(graph_res.edges)
        result.new_links_count = len(graph_res.links)
        result.timings = timings

        return result


# ── Backward-compatible wrapper ───────────────────────────────────────
class MemoryPipeline:
    """Coordinate observation extraction through storage-adjacent steps."""

    def __init__(
        self,
        *,
        extraction_worker: ExtractionWorker | None = None,
        scoring_engine: MemoryScoringEngine | None = None,
    ) -> None:
        self._orchestrator = FastMemoryOrchestrator(
            extraction_worker=extraction_worker,
            scoring_engine=scoring_engine,
        )

    async def process_observation(self, payload: ObservationPayload, session: AsyncSession | None = None) -> Any:
        if session is not None:
            return await self._orchestrator.orchestrate(payload, session)

        extracted = await self._orchestrator._extractor.extract(payload)
        details = []
        for m in extracted:
            sig = ImportanceSignals(
                mention_count=len(m.entities),
                has_emphasis=m.has_emphasis,
                impacts_decisions=m.impacts_decisions,
            )
            score = self._orchestrator._scoring.compute_importance(m.memory_type, m.content, sig)
            if score.rejected:
                details.append({"title": m.title, "status": "skipped_low_value"})
            else:
                details.append({
                    "title": m.title,
                    "status": "ready_for_storage",
                    "importance": score.final_score,
                    "confidence": self._orchestrator._scoring.compute_confidence(m.source_type),
                })
        from contexta.core.pipeline import PipelineResult
        return PipelineResult(
            extracted_count=len(extracted),
            stored_count=sum(1 for item in details if item["status"] == "ready_for_storage"),
            skipped_count=sum(1 for item in details if item["status"] != "ready_for_storage"),
            details=details,
        )


@dataclass
class PipelineResult:
    extracted_count: int
    stored_count: int
    skipped_count: int
    details: list[dict[str, Any]]

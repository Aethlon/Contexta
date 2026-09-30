"""High-speed extraction-to-graph pipeline orchestrator.

Orchestrates memory ingestion, deduplication, in-memory bulk entity resolution,
graph construction, and atomic persistence in cleanly staged, millisecond-timed phases.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from contexta.config.settings import get_settings
from contexta.core.cortex import ContextaCortex
from contexta.core.entities.bulk_resolver import BulkEntityResolver, BulkResolutionResult
from contexta.core.extraction.deduplication import MemoryDeduplicator
from contexta.core.extraction.sensitive_filter import primary_scan
from contexta.core.extraction.worker import ExtractionWorker
from contexta.core.graph.cache import GraphCache
from contexta.core.schemas import ExtractedMemory, ImportanceSignals, ObservationPayload
from contexta.core.scoring.engine import MemoryScoringEngine
from contexta.core.temporal import (
    TemporalMessageContext,
    common_message_context,
    normalize_temporal_messages,
    normalize_temporal_text,
)
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
__all__ = [
    "FastMemoryOrchestrator",
    "MemoryPipeline",
    "PipelineResult",
    "enqueue_embedding_generation",
    "fact_key_for_memory",
    "structural_fact_key",
    "structural_fact_key_from_structured",
]

# Structural fact keys are prefixed so the key families stay tellable apart in
# the column they share: a slot key is `sfx2:<sha256>` and a legacy text-hash key
# is a bare 64-char hex digest. Nothing branches on the prefix -- lookups are
# exact-string matches either way -- but coverage is measurable with
# `fact_key LIKE 'sfx2:%'`, and a structural key can never be mistaken for a
# legacy one by a reader that only knows the old shape.
#
# The prefix is a schema version, not a label. `sfx1:` hashed subject+predicate
# and left the object out; `sfx2:` hashes the whole triple. The two families are
# therefore different functions and a digest can be reused by neither, so the
# bump keeps every pre-existing structural key provably distinct from any new
# one instead of letting a stale `sfx1:` digest alias onto an `sfx2:` slot.
_STRUCTURAL_FACT_KEY_PREFIX = "sfx2:"


def _canonical_component(value: Any) -> str:
    if value is None or isinstance(value, (Mapping, list, tuple, set, bool)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def _slot_digest(slot: str) -> str | None:
    normalized = re.sub(r"\s+", " ", str(slot)).strip().casefold()
    if not normalized:
        return None
    return _STRUCTURAL_FACT_KEY_PREFIX + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def structural_fact_key_from_structured(structured_data: Any) -> str | None:
    """Hash the fact slot named by one ``structured_data`` payload, or None.

    Takes the payload rather than an `ExtractedMemory` so the write path and
    `scripts/backfill_fact_keys.py` resolve slots through one implementation; a
    backfill that recomputed the digest itself would drift from the pipeline the
    moment the canonicalisation changed.

    The slot is the canonicalised ``subject`` + ``predicate`` + ``context`` (when
    present) + ``object``, hashed. The components are normalised before hashing
    so two extractions that differ only in spacing or case land in the same slot;
    an LLM-authored key would otherwise split one fact across two slots.
    """
    structured = structured_data if isinstance(structured_data, Mapping) else {}
    explicit = structured.get("fact_key") or structured.get("truth_key")
    if isinstance(explicit, Mapping) and explicit.get("key"):
        explicit = explicit["key"]
    if explicit:
        return _slot_digest(str(explicit))
    fact = structured.get("fact")
    if not isinstance(fact, Mapping):
        return None
    subject = _canonical_component(fact.get("subject"))
    predicate = _canonical_component(fact.get("predicate"))
    object_value = _canonical_component(fact.get("object"))
    if not subject or not predicate or not object_value:
        return None
    context = _canonical_component(fact.get("context"))
    parts = [subject, predicate] + ([context] if context else []) + [object_value]
    return _slot_digest("\x1f".join(parts))


def structural_fact_key(memory: ExtractedMemory) -> str | None:
    """Hash the fact slot the extractor named, or None when it named none.

    The slot is ``subject`` + ``predicate`` + ``context`` (when present) +
    ``object``, canonicalised and hashed. All three of subject, predicate and
    object are required: a partial triple cannot name a slot, and guessing one
    would let an unrelated memory collide with a stored fact, so it returns None
    and the caller falls back to the legacy text hash. The object is what makes
    the slot nameable, so it is also part of the digest.

    Why the object is in the digest
    ------------------------------
    ``sfx1:`` omitted it, on the theory that a slot is "who, about what" and a
    new value is a correction of that slot. That only holds if the predicate is
    exclusive -- one live value per subject and predicate. It is not, and it is
    not even close. Measured over a 10-conversation ingest: 123 keyed rows
    resolved to 32 slots, and `subject` was the literal string ``"the user"`` in
    all 123, so the digest collapsed to ``sha256("the user" + <coarse verb>)``.
    Four mutually exclusive `uses` facts shared one slot. With
    `uq_memory_record_current_fact_slot` allowing one current row per slot, each
    new arrival closed the previous one: 46 rows written, 28 superseded (61%),
    18 distinct facts reachable, and of 10 sampled supersession pairs, 0 were
    real contradictions and 8 were unrelated (a credential row closed by a code
    snippet, `the user uses multiplication` closed by `the user uses
    function_15`). A slot that collides on unrelated facts does not reconcile
    truth, it deletes it.

    So the slot names the whole assertion. Distinct facts get distinct slots and
    coexist; the index stops being the thing that decides which fact survives.

    The cost, stated plainly
    -----------------------
    A *reworded correction* no longer lands in the same slot. "Salary is 45k"
    and "Actually the salary is $45,000" hash to different slots, so the stale
    row is no longer automatically retired by the unique index. That is now the
    job of `FactSlotContradictionDetector`, which refuses to close a slot unless
    the two values are comparable corrections of the same attribute -- and of the
    extractor's own `status` field, which is the one signal that actually says
    which of two claims is the correction. Supersession is narrower and far less
    frequent than it was; a missed correction shows up as two live rows, which is
    the recoverable direction. Silent deletion of an unrelated fact is not.
    """
    return structural_fact_key_from_structured(memory.structured_data)


def fact_key_for_memory(
    memory: ExtractedMemory,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> str:
    """Resolve which fact slot this memory occupies.

    A structural key names the whole assertion the extractor made -- subject,
    predicate, optional context and object -- so two memories that state the same
    fact however they are phrased keep one key, and two memories that state
    *different* facts never collide on one. The text hash below is only a proxy
    for the slot: a rephrasing changes the key, so the row it should have
    superseded stays current. It stays as the fallback for any extraction
    carrying no usable triple, which is every memory written before the triple
    existed and any memory whose model omitted it.
    """
    structural = structural_fact_key(memory)
    if structural is not None:
        return structural
    memory_type = memory.memory_type.value if hasattr(memory.memory_type, "value") else str(memory.memory_type)
    subject = "|".join(sorted({entity.strip().lower() for entity in memory.entities if entity.strip()}))
    value = " ".join(part.strip().lower() for part in (memory.title, memory.content) if part).strip()
    source = f"{organization_id}:{user_id}:{memory_type}:{subject}:{value}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _redact_nested(value: Any) -> Any:
    """Recursively redact every string leaf of an arbitrary JSON-ish value.

    Mirrors the API gate's nested walk so re-running the gate over an already
    redacted payload is a no-op. Raises whatever primary_scan raises; callers
    treat any raise as a fail-closed rejection.
    """
    if isinstance(value, str):
        scan_result = primary_scan(value)
        return scan_result.redacted_content if scan_result.contains_sensitive_data else value
    if isinstance(value, list):
        return [_redact_nested(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _redact_nested(item) for key, item in value.items()}
    return value


@dataclass
class StageTimings:
    """Millisecond execution latency across orchestrated pipeline stages."""

    cortex_ms: float = 0.0
    extraction_ms: float = 0.0
    deduplication_ms: float = 0.0
    entity_graph_ms: float = 0.0
    persistence_ms: float = 0.0
    total_ms: float = 0.0
    redaction_ms: float = 0.0


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
    embedding_memory_ids: list[str] = field(default_factory=list)


class FastMemoryOrchestrator:
    """High-throughput, millisecond-orchestrated memory and graph pipeline."""

    def __init__(
        self,
        *,
        cortex: ContextaCortex | None = None,
        extraction_worker: ExtractionWorker | None = None,
        scoring_engine: MemoryScoringEngine | None = None,
        graph_cache: GraphCache | None = None,
    ) -> None:
        self._cortex = cortex or ContextaCortex()
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
        ingestion_at = datetime.now(UTC)
        settings = get_settings()

        result = OrchestrationResult()
        timings = StageTimings()

        # ── STAGE -1: PRIMARY REDACTION GATE ─────────────────────────────
        # Every entry point funnels through here, so no path can hand a raw
        # secret to the cortex or the LLM. Purely additive: the API route still
        # runs its own primary_scan, and redaction is idempotent.
        t_redact = time.perf_counter()
        redacted_payload = self._redact_payload(payload)
        timings.redaction_ms = round((time.perf_counter() - t_redact) * 1000, 2)
        if redacted_payload is None:
            # Fail closed: an unusable gate must never degrade into "no redaction".
            result.discarded_count += 1
            result.details.append({
                "action": "redaction_skip",
                "reason": "redaction_gate_unavailable",
                "summary": "observation rejected before extraction: redaction gate failed",
            })
            timings.total_ms = round((time.perf_counter() - t_start) * 1000, 2)
            result.timings = timings
            return result
        payload = redacted_payload

        org_id = payload.organization_id
        user_id = payload.user_id
        session_id = payload.session_id
        now_ts = ingestion_at.replace(tzinfo=None)

        # ── STAGE 0: CONTEXTA CORTEX (JEV DECISION LAYER) ────────────────
        t_cortex = time.perf_counter()
        engine_mode = str(getattr(settings, "engine_mode", "")).lower()
        cortex_settings = getattr(self._cortex, "_settings", None)
        cortex_engine_mode = str(getattr(cortex_settings, "engine_mode", "")).lower()
        if "offline" in {engine_mode, cortex_engine_mode} and isinstance(self._cortex, ContextaCortex):
            cortex_decision = None
        else:
            cortex_decision = await self._cortex.evaluate_observation(payload)
        timings.cortex_ms = round((time.perf_counter() - t_cortex) * 1000, 2)

        # Early candidate skip gate if should_store is False and early skip is enabled
        if (
            cortex_decision is not None
            and not cortex_decision.should_store
            and getattr(settings, "cortex_early_skip_enabled", True)
        ):
            result.discarded_count += 1
            result.details.append({
                "action": "candidate_skip",
                "summary": cortex_decision.derived_summary,
                "telemetry": cortex_decision.telemetry.model_dump(),
            })
            timings.total_ms = round((time.perf_counter() - t_start) * 1000, 2)
            result.timings = timings
            return result

        # ── STAGE 1 & 2: EXTRACTION & SCORING ────────────────────────────
        t0 = time.perf_counter()
        extracted = await self._extractor.extract(payload, cortex_decision=cortex_decision)
        timings.extraction_ms = round((time.perf_counter() - t0) * 1000, 2)
        result.extracted_count = len(extracted)

        if not extracted:
            timings.total_ms = round((time.perf_counter() - t_start) * 1000, 2)
            result.timings = timings
            return result

        normalized_messages = self._normalize_temporal_messages(payload)
        # common_message_context is O(len(messages)) and depends only on the
        # payload, so it is loop-invariant: resolve it once for the whole batch
        # instead of once per extracted memory.
        temporal_context = self._temporal_context_for_payload(payload, normalized_messages)

        # ── STAGE 3: REPOSITORIES & DEDUPLICATION ────────────────────────
        t1 = time.perf_counter()
        memory_repo = MemoryRepository(session, tenant_id=org_id)
        entity_repo = EntityRepository(session, tenant_id=org_id)
        link_repo = MemoryEntityLinkRepository(session, tenant_id=org_id)
        edge_repo = EntityEdgeRepository(session, tenant_id=org_id)
        version_repo = MemoryVersionRepository(session)
        audit_repo = AuditRepository(session, tenant_id=org_id)

        deduplicator = MemoryDeduplicator(memory_repo, version_repository=version_repo)
        truth_engine = TruthMaintenanceEngine(
            memory_repo,
            version_repo,
            edge_repository=edge_repo,
            audit_repository=audit_repo,
        )

        valid_memories: list[tuple[ExtractedMemory, float, float]] = []
        batch_seen: dict[tuple[str, str], ExtractedMemory] = {}
        batch_slots: dict[str, ExtractedMemory] = {}
        for mem in extracted:
            mem = self._ground_memory_temporal(
                mem,
                payload,
                normalized_messages,
                ingestion_at,
                temporal_context,
            )
            batch_key = self._batch_memory_key(mem)
            if batch_key in batch_seen:
                result.merged_count += 1
                result.details.append({
                    "title": mem.title,
                    "action": "merge_in_batch",
                    "existing_id": None,
                })
                continue
            batch_seen[batch_key] = mem
            # One observation cannot open the same fact slot twice. Only one row
            # per slot may be current (uq_memory_record_current_fact_slot), and
            # letting a sibling supersede the other would make the extraction
            # order decide which statement of the slot survives, so the repeat is
            # folded here and reported like the text duplicate above.
            slot_key = self._fact_key_for_memory(mem, org_id, user_id)
            if slot_key in batch_slots:
                result.merged_count += 1
                result.details.append({
                    "title": mem.title,
                    "action": "merge_in_batch",
                    "existing_id": None,
                    "fact_key": slot_key,
                })
                continue
            batch_slots[slot_key] = mem
            dedup = await deduplicator.deduplicate(payload, mem, fact_key=slot_key)
            if dedup.action == "discard":
                result.discarded_count += 1
                result.details.append({"title": mem.title, "action": "discard", "existing_id": str(dedup.existing_id)})
                continue
            if dedup.action == "merge":
                result.merged_count += 1
                result.details.append({"title": mem.title, "action": "merge", "existing_id": str(dedup.existing_id)})
                if dedup.existing_id is not None:
                    result.embedding_memory_ids.append(str(dedup.existing_id))
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

        # ── STAGE 4: TRUTH PLANNING, THEN ENTITY RESOLUTION & GRAPH BUILDING ─
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
                memory_user_id=payload.memory_user_id,
                agent_id=payload.agent_id,
                project_id=payload.project_id,
                organization_id=org_id,
                session_id=session_id,
                memory_type=m_type,
                title=mem.title,
                content=mem.content,
                source_type=s_type,
                confidence=conf,
                importance=imp,
                utility_score=0.0,
                tags=mem.tags,
                structured_data=self._structured_data_for_record(mem),
                memory_state=MemoryState.ACTIVE.value,
                is_pinned=False,
                is_archived=False,
                valid_from=self._valid_from_for_record(mem, ingestion_at),
                valid_to=None,
                event_at=self._aware_datetime(mem.event_at),
                observed_at=self._aware_datetime(mem.observed_at),
                temporal_precision=mem.temporal_precision or "unknown",
                temporal_basis=mem.temporal_basis or "ingestion_fallback",
                fact_key=self._fact_key_for_memory(mem, org_id, user_id),
                lineage_id=self._lineage_id_for_memory(mem, org_id, user_id),
                source_id=self._source_id_for_memory(mem),
                source_message_id=self._source_message_id_for_memory(mem),
                search_text=" ".join(
                    part
                    for part in (mem.title, mem.content, " ".join(mem.tags or []))
                    if part
                ),
                embedding=getattr(mem, "embedding", None),
            )
            mem_records_to_add.append(record)
            mem_pairs.append((rec_id, mem))

        # Claim the fact slots this batch takes over, before anything is
        # inserted. uq_memory_record_current_fact_slot allows one current row
        # per slot, so the incumbent has to be closed before its replacement is
        # inserted, and a pending insert in the session would be autoflushed
        # ahead of the close. The version and audit rows follow the flush below,
        # because memory_version.superseded_by_id references the new row.
        # A sibling from this same observation is a peer, not an older truth:
        # excluding the batch keeps the iteration order of one extraction from
        # deciding which statement of a slot survives.
        batch_ids = frozenset(record.id for record in mem_records_to_add)
        planned_by_record, blocked_ids = await truth_engine.plan_all(
            mem_records_to_add,
            actor_id=user_id,
            exclude_ids=batch_ids,
        )

        # A slot the engine declined to clear is a slot this row cannot enter,
        # and inserting it anyway would abort the whole observation. This runs
        # before the graph is built so a dropped memory leaves no orphan links or
        # edges behind it.
        if blocked_ids:
            kept_records = [rec for rec in mem_records_to_add if rec.id not in blocked_ids]
            kept_ids = {rec.id for rec in kept_records}
            mem_records_to_add = kept_records
            mem_pairs = [pair for pair in mem_pairs if pair[0] in kept_ids]
            for rec_id in blocked_ids:
                result.discarded_count += 1
                result.details.append({
                    "memory_id": str(rec_id),
                    "action": "slot_occupied",
                    "summary": "fact slot still holds a current row; not stored",
                })
            if not mem_records_to_add:
                timings.entity_graph_ms = round((time.perf_counter() - t2) * 1000, 2)
                timings.total_ms = round((time.perf_counter() - t_start) * 1000, 2)
                result.timings = timings
                return result

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

        # 2c. Flush the memory and entity parents before the junction rows.
        # MemoryEntityLink declares bare ForeignKey columns with no
        # relationship(), so the unit of work has no dependency edge between it
        # and memory_record and preserves construction order. Without this flush
        # the link INSERT is emitted before its parent and violates
        # fk_memory_entity_link_memory_id_memory_record.
        await session.flush()

        # 3. Add all links and edges
        if graph_res.links:
            session.add_all(graph_res.links)
        if graph_res.edges:
            # entity_edge now carries uq_entity_edge_identity and
            # ck_entity_edge_no_self_loop, so a concurrent writer can race us to
            # the same relationship. Insert conflict-tolerantly instead of letting
            # a duplicate abort the whole ingestion.
            await bulk_resolver.persist_edges(graph_res.edges)

        # Flush to DB in a single roundtrip
        await session.flush()

        # Apply truth maintenance / supersession: record the lineage now that
        # the new rows exist.
        for rec in mem_records_to_add:
            ent_list = graph_res.memory_to_entities.get(rec.id, [])
            await truth_engine.record(planned_by_record.get(rec.id, ()))
            result.embedding_memory_ids.append(str(rec.id))
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

    @staticmethod
    def _batch_memory_key(memory: ExtractedMemory) -> tuple[str, str]:
        memory_type = memory.memory_type.value if hasattr(memory.memory_type, "value") else str(memory.memory_type)
        text = re.sub(r"\s+", " ", f"{memory.title}\n{memory.content}".casefold()).strip()
        return memory_type, text

    def _redact_payload(self, payload: ObservationPayload) -> ObservationPayload | None:
        """Return a redacted deep copy of the payload, or None if the gate fails.

        This is the pipeline's own choke point. The API route keeps its own
        primary_scan; both gates run primary_scan over the same text, which is
        idempotent, so double redaction is a no-op.

        Coverage mirrors the API gate (messages, metadata, source_id, message_id,
        policy) and additionally covers original_text/normalized_text, which the
        extraction worker forwards verbatim into the LLM prompt and which the API
        gate leaves untouched.

        Fail closed: any error returns None so the caller rejects the observation
        rather than forwarding unredacted content. Never mutates the argument.
        """
        sanitized = payload.model_copy(deep=True)
        try:
            encoded_messages = json.dumps(sanitized.messages, default=str)
            scan_result = primary_scan(encoded_messages)
            if scan_result.contains_sensitive_data:
                # A redacted JSON document that will not parse means we cannot
                # prove the content is clean, so surface the failure instead of
                # silently keeping the original.
                decoded_messages = json.loads(scan_result.redacted_content)
                if not isinstance(decoded_messages, list):
                    raise ValueError("redacted messages did not round-trip to a list")
                sanitized.messages = decoded_messages
            if sanitized.metadata is not None:
                sanitized.metadata = _redact_nested(sanitized.metadata)
            sanitized.source_id = _redact_nested(sanitized.source_id)
            sanitized.message_id = _redact_nested(sanitized.message_id)
            sanitized.policy = _redact_nested(sanitized.policy)
            if sanitized.original_text is not None:
                sanitized.original_text = _redact_nested(sanitized.original_text)
            if sanitized.normalized_text is not None:
                sanitized.normalized_text = _redact_nested(sanitized.normalized_text)
        except Exception:
            logger.exception(
                "Redaction gate failed for session_id=%s user_id=%s; rejecting observation",
                getattr(payload, "session_id", None),
                getattr(payload, "user_id", None),
            )
            return None
        return sanitized

    def _normalize_temporal_messages(self, payload: ObservationPayload) -> list[dict[str, Any]]:
        metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
        return normalize_temporal_messages(
            payload.messages,
            occurred_at=payload.occurred_at or metadata.get("occurred_at"),
            observed_at=payload.observed_at or metadata.get("observed_at"),
            source_id=payload.source_id or metadata.get("source_id"),
            message_id=payload.message_id or metadata.get("message_id"),
            timezone=payload.timezone or metadata.get("timezone") or metadata.get("source_timezone"),
        )

    def _temporal_context_for_payload(
        self,
        payload: ObservationPayload,
        normalized_messages: list[dict[str, Any]],
    ) -> TemporalMessageContext | None:
        """Resolve the batch temporal context shared by every extracted memory.

        Only a function of the payload, so the result is loop-invariant. When the
        messages carry no usable reference we fall back to the payload timestamps.
        """
        context = common_message_context(normalized_messages)
        if context is not None:
            return context
        metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
        occurred_at = self._aware_datetime(payload.occurred_at or metadata.get("occurred_at"))
        observed_at = self._aware_datetime(payload.observed_at or metadata.get("observed_at"))
        reference = occurred_at or observed_at
        if reference is None:
            return None
        source_id = payload.source_id or metadata.get("source_id")
        message_id = payload.message_id or metadata.get("message_id")
        return TemporalMessageContext(
            reference_at=reference,
            occurred_at=occurred_at,
            observed_at=observed_at,
            source_id=str(source_id) if source_id is not None else None,
            message_id=str(message_id) if message_id is not None else None,
            timezone=payload.timezone or "UTC",
            temporal_basis="payload_occurred_at" if occurred_at is not None else "payload_observed_at",
        )

    def _ground_memory_temporal(
        self,
        memory: ExtractedMemory,
        payload: ObservationPayload,
        normalized_messages: list[dict[str, Any]],
        ingestion_at: datetime,
        context: TemporalMessageContext | None = None,
    ) -> ExtractedMemory:
        if context is None:
            context = self._temporal_context_for_payload(payload, normalized_messages)

        timezone = context.timezone if context is not None else (payload.timezone or "UTC")
        reference = context.reference_at if context is not None else None
        # The per-memory pass is kept on purpose. Memory content and title are
        # LLM-authored, not message text, and this pass is normalised against the
        # batch reference rather than the per-message one, so its output is what
        # gets stored. Dropping it would change MemoryRecord.content.
        content_match = normalize_temporal_text(memory.content, reference, timezone)
        title_match = normalize_temporal_text(memory.title, reference, timezone)
        resolved_matches = [
            match
            for match in [*content_match.matches, *title_match.matches]
            if match.resolved_at is not None
        ]

        event_at = self._aware_datetime(memory.event_at)
        observed_at = self._aware_datetime(memory.observed_at)
        if event_at is None and resolved_matches:
            event_at = resolved_matches[0].resolved_at
            precision = memory.temporal_precision or resolved_matches[0].temporal_precision
            basis = memory.temporal_basis or resolved_matches[0].temporal_basis
        elif event_at is None and context is not None and context.reference_at is not None:
            event_at = self._aware_datetime(context.reference_at)
            precision = memory.temporal_precision or "exact"
            basis = memory.temporal_basis or context.temporal_basis
        elif event_at is not None:
            precision = memory.temporal_precision or "exact"
            basis = memory.temporal_basis or "extracted_event_at"
        else:
            precision = memory.temporal_precision or "unknown"
            basis = memory.temporal_basis or "ingestion_fallback"

        if observed_at is None and context is not None:
            observed_at = self._aware_datetime(context.observed_at)
        if observed_at is None:
            observed_at = ingestion_at

        structured_data = memory.structured_data
        expression_matches = resolved_matches
        if not expression_matches and context is not None:
            expression_matches = [match for match in context.matches if match.resolved_at is not None]
        if expression_matches:
            structured = dict(structured_data) if isinstance(structured_data, dict) else {}
            structured.setdefault(
                "temporal_expressions",
                [
                    {
                        "original": match.original_expression,
                        "resolved": match.resolved_at.isoformat() if match.resolved_at else None,
                        "end": match.end_at.isoformat() if match.end_at else None,
                        "precision": match.temporal_precision,
                    }
                    for match in expression_matches
                ],
            )
        else:
            structured = structured_data
        if context is not None and (context.source_id is not None or context.message_id is not None):
            structured = dict(structured) if isinstance(structured, dict) else {}
            structured.setdefault(
                "temporal_source",
                {
                    "reference_at": context.reference_at.isoformat() if context.reference_at else None,
                    "occurred_at": context.occurred_at.isoformat() if context.occurred_at else None,
                    "observed_at": context.observed_at.isoformat() if context.observed_at else None,
                    "source_id": context.source_id,
                    "message_id": context.message_id,
                    "basis": context.temporal_basis,
                },
            )

        return memory.model_copy(
            update={
                "content": content_match.normalized_text,
                "title": title_match.normalized_text,
                "event_at": event_at,
                "observed_at": observed_at,
                "temporal_precision": precision,
                "temporal_basis": basis,
                "structured_data": structured,
            },
        )

    def _aware_datetime(self, value: datetime | str | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, str):
            candidate = value.strip()
            if candidate.endswith(("Z", "z")):
                candidate = f"{candidate[:-1]}+00:00"
            try:
                value = datetime.fromisoformat(candidate)
            except ValueError:
                return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value

    def _valid_from_for_record(self, memory: ExtractedMemory, ingestion_at: datetime) -> datetime:
        source_time = self._aware_datetime(memory.event_at or memory.observed_at)
        return (source_time or ingestion_at).astimezone(UTC).replace(tzinfo=None)

    def _structured_data_for_record(self, memory: ExtractedMemory) -> dict[str, Any]:
        structured = dict(memory.structured_data or {})
        existing_temporal = structured.get("temporal")
        temporal = dict(existing_temporal) if isinstance(existing_temporal, dict) else {}
        event_at = self._aware_datetime(memory.event_at)
        observed_at = self._aware_datetime(memory.observed_at)
        temporal.update(
            {
                "event_at": event_at.isoformat() if event_at is not None else None,
                "observed_at": observed_at.isoformat() if observed_at is not None else None,
                "temporal_precision": memory.temporal_precision or "unknown",
                "temporal_basis": memory.temporal_basis or "ingestion_fallback",
                "temporal_status": "known" if event_at is not None else "unknown",
                "valid_from_basis": (
                    "event_at"
                    if event_at is not None
                    else "observed_at"
                    if memory.temporal_basis not in {None, "ingestion_fallback"}
                    else "ingestion_fallback"
                ),
            },
        )
        structured["temporal"] = temporal
        return structured

    def _fact_key_for_memory(
        self,
        memory: ExtractedMemory,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> str:
        return fact_key_for_memory(memory, organization_id, user_id)

    @staticmethod
    def _structural_fact_key(memory: ExtractedMemory) -> str | None:
        return structural_fact_key(memory)

    def _lineage_id_for_memory(
        self,
        memory: ExtractedMemory,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> str:
        structured = memory.structured_data if isinstance(memory.structured_data, dict) else {}
        explicit = structured.get("lineage_id")
        if explicit:
            return str(explicit)
        return self._fact_key_for_memory(memory, organization_id, user_id)

    def _source_id_for_memory(self, memory: ExtractedMemory) -> str | None:
        structured = memory.structured_data if isinstance(memory.structured_data, dict) else {}
        source = structured.get("temporal_source")
        if isinstance(source, Mapping) and source.get("source_id") is not None:
            return str(source["source_id"])
        return None

    def _source_message_id_for_memory(self, memory: ExtractedMemory) -> str | None:
        structured = memory.structured_data if isinstance(memory.structured_data, dict) else {}
        source = structured.get("temporal_source")
        if isinstance(source, Mapping) and source.get("message_id") is not None:
            return str(source["message_id"])
        return None


# ── Backward-compatible wrapper ───────────────────────────────────────
class MemoryPipeline:
    """Coordinate observation extraction through storage-adjacent steps."""

    def __init__(
        self,
        *,
        cortex: ContextaCortex | None = None,
        extraction_worker: ExtractionWorker | None = None,
        scoring_engine: MemoryScoringEngine | None = None,
    ) -> None:
        self._orchestrator = FastMemoryOrchestrator(
            cortex=cortex,
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

"""Celery tasks for observation extraction processing.

Defines the async task that processes enqueued observation payloads.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from contexta.core.entities.resolver import EntityResolver
from contexta.core.errors import ExtractionError
from contexta.core.extraction.deduplication import MemoryDeduplicator
from contexta.core.extraction.worker import ExtractionWorker
from contexta.core.schemas import ObservationPayload
from contexta.core.scoring.engine import MemoryScoringEngine
from contexta.core.truth.maintenance import TruthMaintenanceEngine
from contexta.db import get_db_session
from contexta.repositories.api_key_repo import ApiKeyRepository
from contexta.repositories.audit_repo import AuditRepository
from contexta.repositories.entity_repo import (
    EntityEdgeRepository,
    EntityRepository,
    MemoryEntityLinkRepository,
)
from contexta.repositories.memory_repo import MemoryRepository
from contexta.repositories.version_repo import MemoryVersionRepository
from contexta.workers.celery_app import celery_app
from contexta.workers.embedding_tasks import enqueue_embedding_generation

logger = logging.getLogger(__name__)


async def _process_observation_async(self, payload: dict[str, Any]) -> dict[str, Any]:
    """Asynchronously run an observation payload through the intelligence pipeline."""
    task_id = self.request.id
    observation = ObservationPayload(**payload)

    org_id = observation.organization_id
    user_id = observation.user_id
    session_id = observation.session_id

    # 1. Run extraction worker (uses LLM to extract memory candidates)
    extracted = await ExtractionWorker().extract(observation)

    processed_details = []

    async with get_db_session() as session:
        # Initialize tenant-scoped repositories
        memory_repo = MemoryRepository(session, tenant_id=org_id)
        entity_repo = EntityRepository(session, tenant_id=org_id)
        link_repo = MemoryEntityLinkRepository(session, tenant_id=org_id)
        edge_repo = EntityEdgeRepository(session, tenant_id=org_id)
        version_repo = MemoryVersionRepository(session)
        audit_repo = AuditRepository(session, tenant_id=org_id)

        # Initialize core engines
        deduplicator = MemoryDeduplicator(memory_repo)
        entity_resolver = EntityResolver(entity_repo, link_repo, edge_repo)
        truth_engine = TruthMaintenanceEngine(
            memory_repo,
            version_repo,
            edge_repository=edge_repo,
            audit_repository=audit_repo,
        )
        scoring_engine = MemoryScoringEngine()

        for memory in extracted:
            # 2. Deduplicate memory candidate against existing truths
            dedup_result = await deduplicator.deduplicate(observation, memory)

            if dedup_result.action == "discard":
                logger.info(
                    "Memory candidate discarded as duplicate: title='%s' existing_id=%s",
                    memory.title,
                    dedup_result.existing_id,
                )
                processed_details.append({
                    "title": memory.title,
                    "action": "discard",
                    "existing_id": str(dedup_result.existing_id),
                })
                continue

            if dedup_result.action == "merge":
                logger.info(
                    "Memory candidate merged with existing memory: title='%s' existing_id=%s",
                    memory.title,
                    dedup_result.existing_id,
                )
                # Merges alter existing content; re-enqueue embedding generation
                enqueue_embedding_generation(str(dedup_result.existing_id))
                processed_details.append({
                    "title": memory.title,
                    "action": "merge",
                    "existing_id": str(dedup_result.existing_id),
                })
                continue

            # 3. Action is "store": persist, resolve entities, maintain truth, embed
            # Importance scoring
            score_breakdown = scoring_engine.compute_importance(memory.memory_type, memory.content)
            confidence = scoring_engine.compute_confidence(memory.source_type)

            # Persist memory record to DB
            persisted_record = await memory_repo.persist(
                user_id=user_id,
                organization_id=org_id,
                session_id=session_id,
                memory=memory,
                confidence=confidence,
                importance=score_breakdown.final_score,
            )

            # Resolve entity mentions and map links
            resolved_entities = await entity_resolver.resolve_memory_entities(
                payload=observation,
                memory_id=persisted_record.id,
                memory=memory,
            )

            # Contradiction check / historical supersession
            await truth_engine.apply(
                persisted_record,
                entity_ids=[re.entity.id for re in resolved_entities],
                actor_id=user_id,
            )

            # Enqueue vector embedding generation
            enqueue_embedding_generation(str(persisted_record.id))

            processed_details.append({
                "title": memory.title,
                "action": "store",
                "memory_id": str(persisted_record.id),
                "importance": score_breakdown.final_score,
                "confidence": confidence,
            })

    return {
        "task_id": task_id,
        "status": "completed",
        "user_id": str(user_id),
        "organization_id": str(org_id),
        "session_id": str(session_id),
        "processed_details": processed_details,
    }


@celery_app.task(
    name="contexta.workers.extraction_tasks.process_observation",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_observation(self, payload: dict[str, Any]) -> dict[str, Any]:
    """Process an enqueued observation payload for memory extraction."""
    task_id = self.request.id
    logger.info("Processing observation: task_id=%s", task_id)

    try:
        return asyncio.run(_process_observation_async(self, payload))
    except PydanticValidationError as exc:
        logger.exception("Invalid observation payload in extraction task: %s", exc)
        raise
    except ExtractionError as exc:
        logger.exception("Observation extraction failed: task_id=%s error=%s", task_id, exc)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception("Observation extraction pipeline failed: task_id=%s error=%s", task_id, exc)
        raise self.retry(exc=exc)

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
from contexta.db import AsyncSessionFactory
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
    """Asynchronously run an observation payload through the high-speed intelligence pipeline."""
    task_id = self.request.id
    observation = ObservationPayload(**payload)

    from contexta.core.pipeline import FastMemoryOrchestrator
    orchestrator = FastMemoryOrchestrator()

    async with AsyncSessionFactory() as session:
        try:
            res = await orchestrator.orchestrate(observation, session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return {
        "task_id": task_id,
        "status": "completed",
        "user_id": str(observation.user_id),
        "organization_id": str(observation.organization_id),
        "session_id": str(observation.session_id),
        "extracted_count": res.extracted_count,
        "stored_count": res.stored_count,
        "new_entities_count": res.new_entities_count,
        "new_edges_count": res.new_edges_count,
        "new_links_count": res.new_links_count,
        "timings": {
            "extraction_ms": res.timings.extraction_ms,
            "deduplication_ms": res.timings.deduplication_ms,
            "entity_graph_ms": res.timings.entity_graph_ms,
            "persistence_ms": res.timings.persistence_ms,
            "total_ms": res.timings.total_ms,
        },
        "processed_details": res.details,
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
    except PydanticValidationError:
        logger.exception("Invalid observation payload in extraction task")
        raise
    except ExtractionError as exc:
        logger.exception("Observation extraction failed: task_id=%s", task_id)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception("Observation extraction pipeline failed: task_id=%s", task_id)
        raise self.retry(exc=exc)


GO_STAGING_BATCH_LIMIT = 100


async def _drain_go_staging_async() -> dict[str, Any]:
    """Drain Go data-plane `observations` staging rows into the memory pipeline.

    Closes the loop: Go receiver writes raw rows (status='active'), Python
    converts each to an ObservationPayload, runs the orchestrator, and marks
    the row status='processed'. Rows with non-UUID tenant/actor ids are marked
    status='skipped' (never retried).
    """
    import uuid as uuid_module

    from sqlalchemy import text

    from contexta.core.pipeline import FastMemoryOrchestrator

    orchestrator = FastMemoryOrchestrator()
    drained = stored = skipped = 0

    async with AsyncSessionFactory() as session:
        try:
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT id, tenant_id, actor_id, content, source, type, "
                            "metadata, tags FROM observations "
                            "WHERE status = 'active' ORDER BY created_at "
                            "LIMIT :limit"
                        ),
                        {"limit": GO_STAGING_BATCH_LIMIT},
                    )
                )
                .mappings()
                .all()
            )
        except Exception:
            logger.info("Go staging table unavailable; skipping drain.")
            return {"status": "skipped", "reason": "no staging table"}

        for row in rows:
            try:
                try:
                    user_id = uuid_module.UUID(str(row["actor_id"]))
                    org_id = uuid_module.UUID(str(row["tenant_id"]))
                except (ValueError, AttributeError, TypeError):
                    await session.execute(
                        text("UPDATE observations SET status = 'skipped' WHERE id = :id"),
                        {"id": row["id"]},
                    )
                    skipped += 1
                    continue

                meta = row["metadata"] or {}
                try:
                    session_id = uuid_module.UUID(str(meta.get("session_id")))
                except (ValueError, AttributeError, TypeError):
                    session_id = uuid_module.uuid4()

                observation = ObservationPayload(
                    user_id=user_id,
                    organization_id=org_id,
                    session_id=session_id,
                    messages=[{"role": "user", "content": row["content"]}],
                    metadata={
                        "source": row["source"],
                        "go_observation_id": str(row["id"]),
                        "tags": row["tags"] or [],
                    },
                )
                res = await orchestrator.orchestrate(observation, session)
                stored += res.stored_count
                await session.execute(
                    text("UPDATE observations SET status = 'processed' WHERE id = :id"),
                    {"id": row["id"]},
                )
                drained += 1
            except Exception:
                logger.exception("Go staging row failed: id=%s", row["id"])
                await session.rollback()
                continue

        await session.commit()

    return {"status": "completed", "drained": drained, "stored": stored, "skipped": skipped}


@celery_app.task(name="contexta.workers.extraction_tasks.drain_go_staging")
def drain_go_staging() -> dict[str, Any]:
    """Celery task draining Go staging observations every minute via beat."""
    logger.info("Draining Go staging observations.")
    try:
        return asyncio.run(_drain_go_staging_async())
    except Exception:
        logger.exception("Go staging drain failed")
        raise

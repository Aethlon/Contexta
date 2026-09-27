from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from contexta.db import AsyncSessionFactory
from contexta.repositories.artifact_repo import ArtifactRepository
from contexta.services.artifact_memory import ArtifactMemoryIngestor
from contexta.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _process_artifact_async(
    artifact_id: str,
    organization_id: str,
    user_id: str,
) -> dict[str, Any]:
    organization_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)
    async with AsyncSessionFactory() as session:
        repository = ArtifactRepository(session, tenant_id=organization_uuid)
        artifact = await repository.get_by_id(UUID(artifact_id))
        if artifact is None:
            return {"status": "not_found", "artifact_id": artifact_id}
        if artifact.organization_id != organization_uuid or artifact.user_id != user_uuid:
            return {"status": "forbidden", "artifact_id": artifact_id}
        result = await ArtifactMemoryIngestor().ingest(artifact, session)
        await session.commit()
        if result.memory_ids:
            from contexta.workers.embedding_tasks import enqueue_embedding_generation

            enqueue_embedding_generation(result.memory_ids)
        return {
            "status": "completed",
            "artifact_id": artifact_id,
            "chunk_count": result.chunk_count,
            "extracted_count": result.extracted_count,
            "memory_count": len(result.memory_ids),
        }


@celery_app.task(
    name="contexta.workers.artifact_tasks.process_artifact",
    bind=True,
    max_retries=3,
    acks_late=True,
)
def process_artifact(
    self,
    artifact_id: str,
    organization_id: str,
    user_id: str,
) -> dict[str, Any]:
    try:
        return asyncio.run(_process_artifact_async(artifact_id, organization_id, user_id))
    except Exception as exc:
        logger.exception("Artifact memory processing failed", extra={"artifact_id": artifact_id})
        raise self.retry(exc=exc)


__all__ = ["process_artifact"]

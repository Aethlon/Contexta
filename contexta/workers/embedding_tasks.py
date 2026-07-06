"""Celery tasks for asynchronous embedding generation."""

import asyncio
import logging
import uuid

from contexta.db import AsyncSessionFactory
from contexta.repositories.memory_repo import MemoryRepository
from contexta.services.embedding import EmbeddingService
from contexta.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _generate_memory_embedding_async(self, memory_id_str: str) -> dict[str, str]:
    """Asynchronous worker implementation to fetch memory, generate, and store embedding."""
    from sqlalchemy import select
    from contexta.models.memory import MemoryRecord

    memory_id = uuid.UUID(memory_id_str)

    async with AsyncSessionFactory() as session:
        try:
            # Query the record bypassing tenant scoping first to find organization_id
            stmt = select(MemoryRecord).where(MemoryRecord.id == memory_id)
            result = await session.execute(stmt)
            memory = result.scalar_one_or_none()

            if not memory:
                logger.error("Memory record not found for embedding generation: %s", memory_id)
                return {
                    "status": "not_found",
                    "memory_id": memory_id_str,
                }

            # Instantiate tenant-scoped repository with the record's organization_id
            repo = MemoryRepository(session, tenant_id=memory.organization_id)

            # Generate and store embedding via service
            service = EmbeddingService(retry_enqueue=None)
            success = await service.generate_and_store(
                memory,
                repo,
                enqueue_on_failure=False,
            )

            if not success:
                raise RuntimeError(f"Embedding generation failed for memory_id={memory_id_str}")

            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return {
        "task_id": self.request.id,
        "memory_id": memory_id_str,
        "status": "completed",
    }


@celery_app.task(
    name="contexta.workers.embedding_tasks.generate_memory_embedding",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def generate_memory_embedding(self, memory_id: str) -> dict[str, str]:
    """Task entry point for memory embedding generation."""
    logger.info(
        "Embedding generation requested: task_id=%s memory_id=%s",
        self.request.id,
        memory_id,
    )
    try:
        return asyncio.run(_generate_memory_embedding_async(self, memory_id))
    except Exception as exc:
        logger.exception(
            "Embedding generation task failed, retrying: task_id=%s memory_id=%s",
            self.request.id,
            memory_id,
        )
        raise self.retry(exc=exc)


def enqueue_embedding_generation(memory_id: str) -> str:
    """Enqueue embedding generation and return the Celery task id."""
    result = generate_memory_embedding.delay(memory_id)
    return str(result.id)

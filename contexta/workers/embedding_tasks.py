"""Celery tasks for asynchronous embedding generation."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import Sequence
from typing import Any

from contexta.db import AsyncSessionFactory
from contexta.models.memory import MemoryContentDecryptionError
from contexta.repositories.memory_repo import MemoryRepository
from contexta.services.embedding import (
    EmbeddingCompatibilityError,
    EmbeddingConfigurationError,
    EmbeddingDimensionError,
    EmbeddingProfileError,
    EmbeddingService,
)
from contexta.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _env_int(default: int, *names: str) -> int:
    for name in names:
        raw = os.environ.get(name)
        if raw is None:
            continue
        try:
            return int(raw)
        except ValueError:
            logger.warning("Invalid integer environment variable %s=%r; using %d", name, raw, default)
    return default


EMBEDDING_TASK_BATCH_SIZE = max(
    1,
    _env_int(
        32,
        "CONTEXTA_EMBEDDING_TASK_BATCH_SIZE",
        "CONTEXTA_EMBEDDING_BATCH_SIZE",
    ),
)
EMBEDDING_TASK_CONCURRENCY = max(
    1,
    _env_int(
        4,
        "CONTEXTA_EMBEDDING_TASK_CONCURRENCY",
        "CONTEXTA_EMBEDDING_CONCURRENCY",
    ),
)


def _normalize_memory_ids(memory_ids: str | uuid.UUID | Sequence[str | uuid.UUID]) -> list[str]:
    values = [memory_ids] if isinstance(memory_ids, (str, uuid.UUID)) else list(memory_ids)
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _task_id(task: Any) -> str | None:
    request = getattr(task, "request", None)
    return str(request.id) if request is not None and request.id else None


def _incompatible_result(memory_id: str, error: Exception) -> dict[str, Any]:
    return {
        "status": "incompatible",
        "memory_id": memory_id,
        "error": str(error),
        "automatic_reembedding": False,
    }


async def _generate_memory_embedding_async(self, memory_id_str: str) -> dict[str, Any]:
    from sqlalchemy import select

    from contexta.models.memory import MemoryRecord

    try:
        memory_id = uuid.UUID(memory_id_str)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid memory_id {memory_id_str!r}; expected a UUID for embedding generation."
        ) from exc

    async with AsyncSessionFactory() as session:
        try:
            result = await session.execute(
                select(MemoryRecord).where(MemoryRecord.id == memory_id)
            )
            memory = result.scalar_one_or_none()
            if not memory:
                logger.error("Memory record not found for embedding generation: %s", memory_id)
                return {
                    "status": "not_found",
                    "memory_id": memory_id_str,
                }
            repository = MemoryRepository(session, tenant_id=memory.organization_id)
            service = EmbeddingService(retry_enqueue=None)
            success = await service.generate_and_store(
                memory,
                repository,
                enqueue_on_failure=False,
            )
            if not success:
                raise RuntimeError(
                    f"Embedding provider failed for memory_id={memory_id_str}; retry is allowed, "
                    "but profile metadata will not be changed."
                )
            await session.commit()
        except (
            EmbeddingCompatibilityError,
            EmbeddingConfigurationError,
            EmbeddingDimensionError,
            EmbeddingProfileError,
            MemoryContentDecryptionError,
        ) as exc:
            await session.rollback()
            logger.error("Embedding generation is incompatible for memory_id=%s: %s", memory_id_str, exc)
            return _incompatible_result(memory_id_str, exc)
        except Exception:
            await session.rollback()
            raise

    return {
        "task_id": _task_id(self),
        "memory_id": memory_id_str,
        "status": "completed",
    }


async def _generate_memory_embedding_batch_async(memory_ids: Sequence[str]) -> dict[str, Any]:
    from sqlalchemy import select

    from contexta.models.memory import MemoryRecord

    ids = list(memory_ids)
    missing = list(ids)
    if not ids:
        return {
            "status": "completed",
            "memory_ids": [],
            "processed_count": 0,
            "not_found": [],
            "incompatible": [],
        }

    async with AsyncSessionFactory() as session:
        try:
            result = await session.execute(select(MemoryRecord).where(MemoryRecord.id.in_(ids)))
            memories_by_id = {str(memory.id): memory for memory in result.scalars().all()}
            memories = [memories_by_id[memory_id] for memory_id in ids if memory_id in memories_by_id]
            missing = [memory_id for memory_id in ids if memory_id not in memories_by_id]
            if not memories:
                return {
                    "status": "completed",
                    "memory_ids": [],
                    "processed_count": 0,
                    "not_found": missing,
                    "incompatible": [],
                }

            service = EmbeddingService(retry_enqueue=None)
            semaphore = asyncio.Semaphore(EMBEDDING_TASK_CONCURRENCY)

            async def generate(memory: Any) -> list[float]:
                async with semaphore:
                    service.ensure_memory_compatible(memory)
                    return await service.embed_memory(memory)

            values = await asyncio.gather(
                *(generate(memory) for memory in memories),
                return_exceptions=True,
            )
            compatible: list[tuple[Any, list[float]]] = []
            incompatible: list[dict[str, Any]] = []
            for memory, value in zip(memories, values):
                if isinstance(
                    value,
                    (
                        EmbeddingCompatibilityError,
                        EmbeddingConfigurationError,
                        EmbeddingDimensionError,
                        EmbeddingProfileError,
                        MemoryContentDecryptionError,
                    ),
                ):
                    incompatible.append(_incompatible_result(str(memory.id), value))
                elif isinstance(value, BaseException):
                    raise value
                else:
                    compatible.append((memory, value))

            processed: list[str] = []
            for memory, embedding in compatible:
                repository = MemoryRepository(session, tenant_id=memory.organization_id)
                try:
                    await service.persist_embedding(memory, repository, embedding)
                except (
                    EmbeddingCompatibilityError,
                    EmbeddingConfigurationError,
                    EmbeddingDimensionError,
                    EmbeddingProfileError,
                    MemoryContentDecryptionError,
                ) as exc:
                    incompatible.append(_incompatible_result(str(memory.id), exc))
                    continue
                processed.append(str(memory.id))
            await session.commit()
        except (EmbeddingConfigurationError, EmbeddingProfileError) as exc:
            await session.rollback()
            return {
                "status": "incompatible",
                "memory_ids": [],
                "processed_count": 0,
                "not_found": missing,
                "incompatible": [_incompatible_result(memory_id, exc) for memory_id in ids],
            }
        except Exception:
            await session.rollback()
            raise

    return {
        "status": "completed",
        "memory_ids": processed,
        "processed_count": len(processed),
        "not_found": missing,
        "incompatible": incompatible,
    }


async def _generate_memory_embeddings_async(
    self,
    memory_ids: str | uuid.UUID | Sequence[str | uuid.UUID],
) -> dict[str, Any]:
    ids = _normalize_memory_ids(memory_ids)
    if not ids:
        return {
            "task_id": _task_id(self),
            "status": "completed",
            "memory_ids": [],
            "processed_count": 0,
            "not_found": [],
            "incompatible": [],
        }

    processed: list[str] = []
    missing: list[str] = []
    incompatible: list[dict[str, Any]] = []
    for start in range(0, len(ids), EMBEDDING_TASK_BATCH_SIZE):
        result = await _generate_memory_embedding_batch_async(ids[start : start + EMBEDDING_TASK_BATCH_SIZE])
        processed.extend(result["memory_ids"])
        missing.extend(result["not_found"])
        incompatible.extend(result["incompatible"])
    return {
        "task_id": _task_id(self),
        "status": "completed",
        "memory_ids": processed,
        "processed_count": len(processed),
        "not_found": missing,
        "incompatible": incompatible,
    }


@celery_app.task(
    name="contexta.workers.embedding_tasks.generate_memory_embedding",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def generate_memory_embedding(
    self,
    memory_id: str | uuid.UUID | Sequence[str | uuid.UUID],
) -> dict[str, Any]:
    normalized = str(memory_id) if isinstance(memory_id, uuid.UUID) else memory_id
    logger.info(
        "Embedding generation requested: task_id=%s memory_id=%s",
        _task_id(self),
        memory_id,
    )
    try:
        if not isinstance(normalized, str):
            return asyncio.run(_generate_memory_embeddings_async(self, normalized))
        return asyncio.run(_generate_memory_embedding_async(self, normalized))
    except Exception as exc:
        logger.exception(
            "Embedding generation task failed, retrying: task_id=%s memory_id=%s",
            _task_id(self),
            memory_id,
        )
        raise self.retry(exc=exc)


@celery_app.task(
    name="contexta.workers.embedding_tasks.generate_memory_embeddings",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def generate_memory_embeddings(
    self,
    memory_ids: str | uuid.UUID | Sequence[str | uuid.UUID],
) -> dict[str, Any]:
    ids = _normalize_memory_ids(memory_ids)
    logger.info(
        "Batch embedding generation requested: task_id=%s count=%s",
        _task_id(self),
        len(ids),
    )
    try:
        return asyncio.run(_generate_memory_embeddings_async(self, ids))
    except Exception as exc:
        logger.exception(
            "Batch embedding generation task failed, retrying: task_id=%s count=%s",
            _task_id(self),
            len(ids),
        )
        raise self.retry(exc=exc)


def enqueue_embedding_generation(
    memory_id: str | uuid.UUID | Sequence[str | uuid.UUID],
) -> str:
    if isinstance(memory_id, (str, uuid.UUID)):
        result = generate_memory_embedding.delay(str(memory_id))
    else:
        result = generate_memory_embeddings.delay([str(value) for value in memory_id])
    return str(result.id)


def enqueue_embedding_generations(memory_ids: Sequence[str | uuid.UUID]) -> str:
    result = generate_memory_embeddings.delay([str(value) for value in memory_ids])
    return str(result.id)


enqueue_embedding_generation_batch = enqueue_embedding_generations

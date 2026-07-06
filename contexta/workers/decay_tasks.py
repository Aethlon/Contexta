"""Celery tasks for memory decay."""

import asyncio
import logging
from sqlalchemy import select

from contexta.core.decay.engine import DecayEngine
from contexta.db import AsyncSessionFactory
from contexta.models.memory import MemoryRecord
from contexta.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _run_decay_cycle_async() -> dict:
    """Query and apply decay transitions to all applicable memories."""
    decay_engine = DecayEngine()

    async with AsyncSessionFactory() as session:
        try:
            # Select all unpinned, active/warm/cold, unarchived, non-superseded records globally
            stmt = select(MemoryRecord).where(
                MemoryRecord.is_pinned == False,  # noqa: E712
                MemoryRecord.is_archived == False,  # noqa: E712
                MemoryRecord.valid_to.is_(None),
            )
            result = await session.execute(stmt)
            memories = result.scalars().all()

            updates_count = 0
            for memory in memories:
                new_state = decay_engine.transition_for(memory)
                if new_state != memory.memory_state:
                    logger.info(
                        "Decaying memory_id=%s from %s to %s",
                        memory.id,
                        memory.memory_state,
                        new_state,
                    )
                    memory.memory_state = new_state
                    updates_count += 1

            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return {
        "status": "completed",
        "processed_memories": len(memories),
        "updated_memories": updates_count,
    }


@celery_app.task(name="contexta.workers.decay_tasks.run_decay_cycle")
def run_decay_cycle() -> dict:
    """Celery task to run the memory decay cycle."""
    logger.info("Starting memory decay cycle task.")
    try:
        return asyncio.run(_run_decay_cycle_async())
    except Exception as exc:
        logger.exception("Memory decay cycle task failed: %s", exc)
        raise

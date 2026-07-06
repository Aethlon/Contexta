"""Celery tasks for reflection maintenance."""

import asyncio
import logging
from sqlalchemy import select

from contexta.core.reflection.engine import ReflectionEngine
from contexta.db import get_db_session
from contexta.models.memory import MemoryRecord
from contexta.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _run_reflection_cycle_async() -> dict:
    """Run reflection engine analysis on unpinned goals to transition dormant ones."""
    reflection = ReflectionEngine()

    async with get_db_session() as session:
        # Load active, unpinned, non-archived goal memories globally
        stmt = select(MemoryRecord).where(
            MemoryRecord.memory_type == "goal",
            MemoryRecord.is_pinned == False,  # noqa: E712
            MemoryRecord.is_archived == False,  # noqa: E712
            MemoryRecord.valid_to.is_(None),
        )
        result = await session.execute(stmt)
        memories = result.scalars().all()

        updated_count = 0
        for memory in memories:
            old_state = memory.memory_state
            old_importance = memory.importance
            reflection.mark_dormant_goal(memory)
            if memory.memory_state != old_state or memory.importance != old_importance:
                logger.info(
                    "Reflection marked goal memory_id=%s as dormant: state %s -> %s, importance %s -> %s",
                    memory.id,
                    old_state,
                    memory.memory_state,
                    old_importance,
                    memory.importance,
                )
                updated_count += 1

    return {
        "status": "completed",
        "processed_memories": len(memories),
        "updated_memories": updated_count,
    }


@celery_app.task(name="contexta.workers.reflection_tasks.run_reflection_cycle")
def run_reflection_cycle() -> dict:
    """Celery task to run the memory reflection cycle."""
    logger.info("Starting memory reflection cycle task.")
    try:
        return asyncio.run(_run_reflection_cycle_async())
    except Exception as exc:
        logger.exception("Memory reflection cycle task failed: %s", exc)
        raise

"""Coverage for required task batch 11.3 through 24.3."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contexta.core.context.builder import ContextBuilder
from contexta.core.context.planner import ContextPlanner
from contexta.core.decay.engine import DecayEngine
from contexta.core.dream.engine import DreamCycleEngine
from contexta.core.lifecycle.engine import MemoryLifecycleEngine
from contexta.core.reflection.engine import ReflectionEngine
from contexta.core.schemas import ContextRequest
from contexta.models.memory import MemoryRecord


class FakeLifecycleRepo:
    def __init__(self) -> None:
        self.updates = []
        self.deletes = []

    async def update_by_id(self, record_id, values):
        self.updates.append((record_id, values))
        return 1

    async def delete_by_id(self, record_id):
        self.deletes.append(record_id)
        return 1


def memory(memory_type: str = "fact", importance: float = 0.5) -> MemoryRecord:
    now = datetime.now(UTC)
    return MemoryRecord(
        id=uuid4(),
        user_id=uuid4(),
        organization_id=uuid4(),
        memory_type=memory_type,
        title="Memory",
        content="useful content",
        source_type="user_explicit",
        confidence=1.0,
        importance=importance,
        created_at=now,
        updated_at=now,
        is_archived=False,
        valid_to=None,
    )


def test_context_planner_and_builder_order_and_usage() -> None:
    planner = ContextPlanner()
    allocation = planner.allocate(100)
    assert allocation.allocations["projects"] == 35

    builder = ContextBuilder(planner)
    project = memory("project", 0.9)
    fact = memory("fact", 0.4)
    request = ContextRequest(user_id=project.user_id, organization_id=project.organization_id, session_id=uuid4())
    request.config.token_budget = 100
    context = builder.build(request, [fact, project])
    assert context.active_projects[0]["importance"] == 0.9
    assert "token_usage" in context.metadata


async def test_lifecycle_engine_calls_scoped_repository() -> None:
    repo = FakeLifecycleRepo()
    engine = MemoryLifecycleEngine(repo)
    memory_id = uuid4()

    await engine.pin(memory_id)
    await engine.archive(memory_id)
    await engine.delete(memory_id)

    assert repo.updates == [
        (memory_id, {"is_pinned": True}),
        (memory_id, {"is_archived": True}),
    ]
    assert repo.deletes == [memory_id]


def test_decay_reflection_and_dream_engines() -> None:
    now = datetime.now(UTC)
    stale = memory("goal", 0.8)
    stale.updated_at = now - timedelta(days=181)
    stale.last_accessed_at = None
    stale.memory_state = "active"
    stale.is_pinned = False

    assert DecayEngine().transition_for(stale, now=now) == "warm"
    reflected = ReflectionEngine().mark_dormant_goal(stale, now=now)
    assert reflected.importance == 0.5

    gap = DreamCycleEngine().identify_gap(
        organization_id=uuid4(),
        user_id=uuid4(),
        question="What is missing?",
        related_entity_id=uuid4(),
        confidence=0.2,
    )
    assert gap is not None
    assert gap.status == "open"

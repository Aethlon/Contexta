"""Memory context, lifecycle, and explainability routes."""

from uuid import UUID

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.db import get_db_session
from contexta.core.schemas import ContextConfig, ContextRequest
from contexta.core.context.builder import ContextBuilder
from contexta.repositories.memory_repo import MemoryRepository
from contexta.models.memory import MemoryRecord
from contexta.models.version import MemoryVersion

router = APIRouter()


class MemoryListResponse(BaseModel):
    id: str
    title: str
    memory_type: str
    memory_state: str
    importance: float
    confidence: float
    tags: list[str] | None
    is_pinned: bool
    is_archived: bool
    created_at: str | None
    updated_at: str | None


class MemoryDetailResponse(BaseModel):
    id: str
    user_id: str
    organization_id: str
    memory_type: str
    title: str
    content: str
    structured_data: dict | None
    source_type: str
    confidence: float
    importance: float
    utility_score: float
    tags: list[str] | None
    session_id: str | None
    memory_state: str
    is_pinned: bool
    is_archived: bool
    valid_from: str | None
    valid_to: str | None
    created_at: str | None
    updated_at: str | None
    last_accessed_at: str | None


@router.get("")
async def list_memories(
    user_id: UUID | None = None,
    memory_type: str | None = None,
    state: str | None = None,
    pinned: bool | None = None,
    archived: bool | None = None,
    offset: int = 0,
    limit: int = 50,
    request: Request = None,
    session: AsyncSession = Depends(get_db_session),
) -> list[MemoryListResponse]:
    """List memories with optional filters."""
    org_id = UUID(str(request.state.organization_id))
    repo = MemoryRepository(session, tenant_id=org_id)

    stmt = select(MemoryRecord)
    if user_id:
        stmt = stmt.where(MemoryRecord.user_id == user_id)
    if memory_type:
        stmt = stmt.where(MemoryRecord.memory_type == memory_type)
    if state:
        stmt = stmt.where(MemoryRecord.memory_state == state)
    if pinned is not None:
        stmt = stmt.where(MemoryRecord.is_pinned == pinned)
    if archived is not None:
        stmt = stmt.where(MemoryRecord.is_archived == archived)
    stmt = stmt.order_by(MemoryRecord.created_at.desc()).offset(offset).limit(limit)
    stmt = repo._scope_select(stmt)
    result = await session.execute(stmt)
    memories = result.scalars().all()

    return [
        MemoryListResponse(
            id=str(m.id),
            title=m.title,
            memory_type=m.memory_type,
            memory_state=m.memory_state,
            importance=m.importance,
            confidence=m.confidence,
            tags=m.tags,
            is_pinned=m.is_pinned,
            is_archived=m.is_archived,
            created_at=m.created_at.isoformat() if m.created_at else None,
            updated_at=m.updated_at.isoformat() if m.updated_at else None,
        )
        for m in memories
    ]


@router.get("/{memory_id}")
async def get_memory(
    memory_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> MemoryDetailResponse:
    """Get full details for a single memory record."""
    org_id = UUID(str(request.state.organization_id))
    repo = MemoryRepository(session, tenant_id=org_id)
    memory = await repo.get_by_id(memory_id)
    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    return MemoryDetailResponse(
        id=str(memory.id),
        user_id=str(memory.user_id),
        organization_id=str(memory.organization_id),
        memory_type=memory.memory_type,
        title=memory.title,
        content=memory.content,
        structured_data=memory.structured_data,
        source_type=memory.source_type,
        confidence=memory.confidence,
        importance=memory.importance,
        utility_score=memory.utility_score,
        tags=memory.tags,
        session_id=str(memory.session_id) if memory.session_id else None,
        memory_state=memory.memory_state,
        is_pinned=memory.is_pinned,
        is_archived=memory.is_archived,
        valid_from=memory.valid_from.isoformat() if memory.valid_from else None,
        valid_to=memory.valid_to.isoformat() if memory.valid_to else None,
        created_at=memory.created_at.isoformat() if memory.created_at else None,
        updated_at=memory.updated_at.isoformat() if memory.updated_at else None,
        last_accessed_at=memory.last_accessed_at.isoformat() if memory.last_accessed_at else None,
    )


@router.get("/context")
async def get_context(
    user_id: UUID,
    organization_id: UUID,
    session_id: UUID,
    request: Request,
    token_budget: int | None = None,
    include_user_model: bool = True,
    num_recent_messages: int = 10,
    num_relevant_memories: int = 20,
    graph_depth: int = 2,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Retrieve and assemble token-budgeted memory context for an agent session."""
    org_id = UUID(str(request.state.organization_id))
    if organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: organization_id mismatch.",
        )

    # 1. Fetch current truths (active, valid) for the user
    repo = MemoryRepository(session, tenant_id=org_id)
    memories = await repo.get_current_truths(user_id, limit=200)

    # 2. Build context using ContextBuilder
    config = ContextConfig(
        num_recent_messages=num_recent_messages,
        num_relevant_memories=num_relevant_memories,
        graph_depth=graph_depth,
        include_user_model=include_user_model,
        token_budget=token_budget,
    )
    context_req = ContextRequest(
        user_id=user_id,
        organization_id=organization_id,
        session_id=session_id,
        config=config,
    )

    newest_ts = None
    if memories:
        timestamps = [m.created_at for m in memories if m.created_at]
        if timestamps:
            newest_ts = max(timestamps).isoformat()

    builder = ContextBuilder()
    built = builder.build(
        request=context_req,
        memories=list(memories),
        newest_memory_timestamp=newest_ts,
    )

    return {
        "user_profile": built.user_profile,
        "active_projects": built.active_projects,
        "preferences": built.preferences,
        "goals": built.goals,
        "recent_events": built.recent_events,
        "relevant_memories": built.relevant_memories,
        "token_usage": built.metadata.get("token_usage", {"total": 0, "by_section": {}}),
        "cache_hit": False,
        "request_id": request.headers.get("x-request-id", "01J"),
    }


@router.post("/{memory_id}/pin")
async def pin_memory(
    memory_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Pin a memory to exclude it from the decay process."""
    org_id = UUID(str(request.state.organization_id))
    repo = MemoryRepository(session, tenant_id=org_id)
    rows = await repo.update_by_id(memory_id, {"is_pinned": True})
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    return {"memory_id": str(memory_id), "is_pinned": True}


@router.post("/{memory_id}/unpin")
async def unpin_memory(
    memory_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Unpin a memory, allowing it to decay normally."""
    org_id = UUID(str(request.state.organization_id))
    repo = MemoryRepository(session, tenant_id=org_id)
    rows = await repo.update_by_id(memory_id, {"is_pinned": False})
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    return {"memory_id": str(memory_id), "is_pinned": False}


@router.post("/{memory_id}/archive")
async def archive_memory(
    memory_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Archive a memory to hide it from standard retrieval."""
    org_id = UUID(str(request.state.organization_id))
    repo = MemoryRepository(session, tenant_id=org_id)
    rows = await repo.update_by_id(memory_id, {"is_archived": True})
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    return {"memory_id": str(memory_id), "is_archived": True}


@router.post("/{memory_id}/restore")
async def restore_memory(
    memory_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Restore an archived memory back to active state."""
    org_id = UUID(str(request.state.organization_id))
    repo = MemoryRepository(session, tenant_id=org_id)
    rows = await repo.update_by_id(memory_id, {"is_archived": False})
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    return {"memory_id": str(memory_id), "is_archived": False}


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Permanently delete a memory record."""
    org_id = UUID(str(request.state.organization_id))
    repo = MemoryRepository(session, tenant_id=org_id)
    rows = await repo.delete_by_id(memory_id)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    return {"memory_id": str(memory_id), "deleted": True}


@router.get("/{memory_id}/explain")
async def explain_memory(
    memory_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Retrieve scoring breakdown and supersession history for a memory."""
    org_id = UUID(str(request.state.organization_id))
    repo = MemoryRepository(session, tenant_id=org_id)
    memory = await repo.get_by_id(memory_id)
    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    # Query historical versions
    stmt = (
        select(MemoryVersion)
        .where(MemoryVersion.memory_id == memory_id)
        .order_by(MemoryVersion.created_at.desc())
    )
    result = await session.execute(stmt)
    versions = result.scalars().all()

    return {
        "memory_id": str(memory.id),
        "source": {
            "source_type": memory.source_type,
            "session_id": str(memory.session_id) if memory.session_id else None,
        },
        "classification": {
            "memory_type": memory.memory_type,
            "tags": memory.tags or [],
        },
        "scoring": {
            "confidence": memory.confidence,
            "importance": memory.importance,
            "utility_score": memory.utility_score,
        },
        "supersession_history": [
            {
                "id": str(v.id),
                "content": v.content,
                "importance": v.importance,
                "valid_from": v.valid_from.isoformat() if v.valid_from else None,
                "valid_to": v.valid_to.isoformat() if v.valid_to else None,
                "superseded_by_id": str(v.superseded_by_id) if v.superseded_by_id else None,
            }
            for v in versions
        ],
    }


@router.get("/timeline/{user_id}")
async def timeline(
    user_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Retrieve a chronological list of memory events for a user."""
    org_id = UUID(str(request.state.organization_id))
    repo = MemoryRepository(session, tenant_id=org_id)

    # Fetch user memories scoped to tenant
    stmt = (
        select(MemoryRecord)
        .where(MemoryRecord.user_id == user_id)
        .order_by(MemoryRecord.created_at.desc())
        .limit(50)
    )
    stmt = repo._scope_select(stmt)
    result = await session.execute(stmt)
    memories = result.scalars().all()

    events = []
    for m in memories:
        event_type = "created"
        if m.is_archived:
            event_type = "archived"
        elif m.valid_to is not None:
            event_type = "superseded"

        events.append({
            "id": str(m.id),
            "event_type": event_type,
            "timestamp": m.created_at.isoformat() if m.created_at else None,
            "memory": {
                "title": m.title,
                "content": m.content,
                "memory_type": m.memory_type,
                "is_pinned": m.is_pinned,
                "is_archived": m.is_archived,
                "memory_state": m.memory_state,
            },
        })

    return {"user_id": str(user_id), "events": events}


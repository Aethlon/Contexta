"""Session management routes."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.db import get_db_session
from contexta.models.session import Session
from contexta.repositories.session_repo import SessionRepository
from contexta.repositories.memory_repo import MemoryRepository
from pydantic import BaseModel

router = APIRouter()


class SessionCreate(BaseModel):
    user_id: UUID
    organization_id: UUID
    metadata: dict | None = None


@router.post("")
async def create_session(
    payload: SessionCreate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Initialize a conversation session, persisting it to database."""
    org_id = UUID(str(request.state.organization_id))
    if payload.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: organization_id mismatch.",
        )

    repo = SessionRepository(session, tenant_id=org_id)
    new_session = Session(
        id=uuid4(),
        user_id=payload.user_id,
        organization_id=org_id,
        started_at=datetime.utcnow(),
        metadata_=payload.metadata,
    )
    created = await repo.create(new_session)

    return {
        "session_id": str(created.id),
        "user_id": str(created.user_id),
        "organization_id": str(created.organization_id),
        "started_at": created.started_at.isoformat(),
    }


@router.post("/{session_id}/end")
async def end_session(
    session_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Close a session, setting its ended_at timestamp."""
    org_id = UUID(str(request.state.organization_id))
    repo = SessionRepository(session, tenant_id=org_id)

    db_session = await repo.get_by_id(session_id)
    if not db_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    ended_at = datetime.utcnow()
    await repo.update_by_id(session_id, {"ended_at": ended_at})

    return {
        "session_id": str(session_id),
        "ended_at": ended_at.isoformat(),
        "epilogue_worker": "queued",
    }


@router.get("/inspect/{user_id}")
async def inspect_user(
    user_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Retrieve all sessions and their generated memories for a specific user."""
    org_id = UUID(str(request.state.organization_id))
    session_repo = SessionRepository(session, tenant_id=org_id)
    user_sessions = await session_repo.get_by_user(user_id)

    memory_repo = MemoryRepository(session, tenant_id=org_id)
    sessions_data = []

    for s in user_sessions:
        memories = await memory_repo.get_by_session(s.id)
        sessions_data.append({
            "session_id": str(s.id),
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "metadata": s.metadata_,
            "memories_count": len(memories),
            "memories": [
                {
                    "id": str(m.id),
                    "title": m.title,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in memories
            ],
        })

    return {"user_id": str(user_id), "sessions": sessions_data}


@router.get("/{session_id}")
async def get_session(
    session_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Retrieve details and statistics for a single session."""
    org_id = UUID(str(request.state.organization_id))
    session_repo = SessionRepository(session, tenant_id=org_id)
    db_session = await session_repo.get_by_id(session_id)
    if not db_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    memory_repo = MemoryRepository(session, tenant_id=org_id)
    memories = await memory_repo.get_by_session(session_id)

    earliest_memory_created_at = None
    if memories:
        timestamps = [m.created_at for m in memories if m.created_at]
        if timestamps:
            earliest_memory_created_at = min(timestamps).isoformat()

    return {
        "session_id": str(session_id),
        "user_id": str(db_session.user_id),
        "organization_id": str(db_session.organization_id),
        "started_at": db_session.started_at.isoformat() if db_session.started_at else None,
        "ended_at": db_session.ended_at.isoformat() if db_session.ended_at else None,
        "metadata": db_session.metadata_,
        "memory_count": len(memories),
        "earliest_memory_created_at": earliest_memory_created_at,
    }


"""Audit log inspection routes for the Contexta dashboard."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.db import get_db_session
from contexta.models.audit import AuditLog
from contexta.repositories.audit_repo import AuditRepository

router = APIRouter(prefix="/v1/audit", tags=["audit"])


class AuditLogResponse(BaseModel):
    """Audit log entry representation."""

    id: UUID
    organization_id: UUID
    actor_id: UUID
    operation_type: str
    target_id: UUID | None = None
    details: dict | None = None
    created_at: datetime


def _resolve_organization_id(
    organization_id: UUID | None,
    x_organization_id: str | None,
    x_org_id: str | None = None,
    state_org_id: str | None = None,
) -> UUID:
    raw = str(organization_id) if organization_id else (x_organization_id or x_org_id or state_org_id)
    if not raw:
        # Fallback to default tenant if not specified (local dev / single node OSS)
        return UUID("00000000-0000-0000-0000-000000000001")
    try:
        return UUID(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="organization_id must be a valid UUID.",
        ) from exc


@router.get("", response_model=list[AuditLogResponse])
@router.get("/", response_model=list[AuditLogResponse])
async def list_audit_logs(
    request: Request,
    organization_id: UUID | None = None,
    x_organization_id: str | None = Header(default=None),
    x_org_id: str | None = Header(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> list[AuditLogResponse]:
    """List recent audit logs for the authenticated organization."""
    org_id = _resolve_organization_id(
        organization_id,
        x_organization_id,
        x_org_id,
        getattr(request.state, "organization_id", None),
    )

    repo = AuditRepository(session, tenant_id=org_id)

    # Query with tenant scoping, ordered by created_at DESC
    stmt = (
        select(AuditLog)
        .where(AuditLog.organization_id == org_id)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    scalars = result.scalars()
    if hasattr(scalars, "__await__"):
        scalars = await scalars
    records = scalars.all() if hasattr(scalars, "all") else []
    if hasattr(records, "__await__"):
        records = await records

    return [
        AuditLogResponse(
            id=rec.id,
            organization_id=rec.organization_id,
            actor_id=rec.actor_id,
            operation_type=rec.operation_type,
            target_id=rec.target_id,
            details=rec.details,
            created_at=rec.created_at,
        )
        for rec in records
    ]

"""API-key management routes for hosted contexta accounts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.db import get_db_session
from contexta.models.api_key import ApiKeyRecord
from contexta.repositories.api_key_repo import ApiKeyRepository

router = APIRouter(prefix="/v1/keys", tags=["api keys"])


class ApiKeyCreateRequest(BaseModel):
    """Payload for creating an organization-scoped API key."""

    name: str = Field(default="Agent key", min_length=1, max_length=120)
    organization_id: UUID
    actor_id: UUID
    scopes: list[str] = Field(default_factory=lambda: ["observe", "retrieve"])


class ApiKeyResponse(BaseModel):
    """API key metadata returned to the dashboard."""

    id: UUID
    name: str
    prefix: str
    organization_id: UUID
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None = None


class ApiKeyCreateResponse(BaseModel):
    """Creation response with the one-time API token."""

    token: str
    key: ApiKeyResponse


def _record_to_response(record: ApiKeyRecord) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=record.id,
        name=record.name,
        prefix=record.prefix,
        organization_id=record.organization_id,
        scopes=list(record.scopes),
        created_at=record.created_at,
        last_used_at=record.last_used_at,
    )


def _resolve_organization_id(
    organization_id: UUID | None,
    x_organization_id: str | None,
) -> UUID:
    raw = str(organization_id) if organization_id else x_organization_id
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization_id is required.",
        )
    try:
        return UUID(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="organization_id must be a valid UUID.",
        ) from exc


@router.get("", response_model=list[ApiKeyResponse])
async def list_keys(
    organization_id: UUID | None = None,
    x_organization_id: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> list[ApiKeyResponse]:
    """Return API-key metadata for an organization."""
    tenant_id = _resolve_organization_id(organization_id, x_organization_id)
    repo = ApiKeyRepository(session, tenant_id)
    records = await repo.list_by_org()
    return [_record_to_response(record) for record in records]


@router.post("", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_key(
    payload: ApiKeyCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ApiKeyCreateResponse:
    """Create an organization-scoped API key.

    The full token is returned once. Only a hash and display prefix are stored.
    """
    repo = ApiKeyRepository(session, payload.organization_id)
    created = await repo.create_key(
        name=payload.name,
        actor_id=payload.actor_id,
        scopes=payload.scopes,
    )
    return ApiKeyCreateResponse(
        token=created.token,
        key=_record_to_response(created.record),
    )

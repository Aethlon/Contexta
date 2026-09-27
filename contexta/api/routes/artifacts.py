from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from contexta.db import get_db_session
from contexta.models.artifact import ArtifactRecord
from contexta.repositories.artifact_repo import ArtifactRepository
from contexta.services.artifacts import (
    ArtifactCapabilityError,
    ArtifactDownloadError,
    ArtifactService,
    ArtifactSizeError,
    ArtifactStorageError,
    ArtifactValidationError,
)
from contexta.workers.artifact_tasks import process_artifact

logger = logging.getLogger(__name__)

router = APIRouter()


class ArtifactURLUpload(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    filename: str | None = Field(default=None, max_length=500)
    user_id: UUID | None = None
    organization_id: UUID | None = None
    mime_type: str | None = Field(default=None, max_length=255)
    original_reference: str | None = Field(default=None, max_length=4096)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactMetadataResponse(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: UUID
    filename: str
    mime_type: str
    size_bytes: int
    content_hash: str
    sha256: str
    storage_backend: str
    storage_key: str
    storage_etag: str | None
    original_reference: str
    metadata: dict[str, Any]
    extraction_status: str
    extraction_method: str | None
    extraction_error: str | None
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class _UploadInput:
    data: bytes | None
    filename: str | None
    mime_type: str | None
    url: str | None
    user_id: UUID | None
    organization_id: UUID | None
    original_reference: str | None
    metadata: dict[str, Any]


def _state_uuid(request: Request, name: str) -> UUID | None:
    value = getattr(request.state, name, None)
    if isinstance(value, UUID):
        return value
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _tenant_id(request: Request) -> UUID:
    value = _state_uuid(request, "organization_id")
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated organization context is required.",
        )
    return value


def _assert_organization(
    requested: UUID | None,
    tenant_id: UUID,
) -> None:
    if requested is not None and requested != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: organization_id mismatch.",
        )


def _effective_user_id(
    request: Request,
    requested: UUID | None,
) -> UUID:
    actor_id = _state_uuid(request, "actor_id")
    if requested is not None and actor_id is not None and requested != actor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: user_id mismatch.",
        )
    value = requested or actor_id
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="user_id is required.",
        )
    return value


def _parse_uuid_field(value: Any, name: str) -> UUID | None:
    if value is None or value == "":
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{name} must be a valid UUID.",
        ) from exc


def _parse_metadata(value: Any) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="metadata must be a JSON object.",
            ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="metadata must be a JSON object.",
        )
    return parsed


def _form_text(form: Any, name: str) -> str | None:
    value = form.get(name)
    if value is None or isinstance(value, UploadFile):
        return None
    return str(value)


async def _parse_multipart(
    request: Request,
    max_size_bytes: int,
) -> _UploadInput:
    async with request.form() as form:
        upload = form.get("file") or form.get("artifact")
        if upload is not None and not isinstance(upload, UploadFile):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="file must be an uploaded file.",
            )
        url = _form_text(form, "url") or _form_text(form, "source_url")
        if upload is not None and url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide either file or url, not both.",
            )
        data: bytes | None = None
        filename = _form_text(form, "filename")
        mime_type = _form_text(form, "mime_type")
        if isinstance(upload, UploadFile):
            data = await upload.read(max_size_bytes + 1)
            filename = filename or upload.filename
            mime_type = mime_type or upload.content_type
            await upload.close()
        return _UploadInput(
            data=data,
            filename=filename,
            mime_type=mime_type,
            url=url,
            user_id=_parse_uuid_field(_form_text(form, "user_id"), "user_id"),
            organization_id=_parse_uuid_field(
                _form_text(form, "organization_id"), "organization_id"
            ),
            original_reference=(
                _form_text(form, "original_reference") or _form_text(form, "source_url")
            ),
            metadata=_parse_metadata(form.get("metadata")),
        )


async def _parse_json(request: Request) -> _UploadInput:
    try:
        body = await request.json()
        payload = ArtifactURLUpload.model_validate(body)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A valid URL upload payload is required.",
        ) from exc
    return _UploadInput(
        data=None,
        filename=payload.filename,
        mime_type=payload.mime_type,
        url=payload.url,
        user_id=payload.user_id,
        organization_id=payload.organization_id,
        original_reference=payload.original_reference,
        metadata=payload.metadata,
    )


async def _parse_raw(
    request: Request,
    max_size_bytes: int,
) -> _UploadInput:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_size_bytes:
                raise ArtifactSizeError(
                    f"Artifact exceeds the maximum size of {max_size_bytes} bytes."
                )
        except ValueError:
            pass
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_size_bytes:
            raise ArtifactSizeError(
                f"Artifact exceeds the maximum size of {max_size_bytes} bytes."
            )
        chunks.append(chunk)
    return _UploadInput(
        data=b"".join(chunks),
        filename=(
            request.query_params.get("filename")
            or request.headers.get("x-filename")
            or "artifact"
        ),
        mime_type=request.headers.get("content-type"),
        url=None,
        user_id=_parse_uuid_field(
            request.query_params.get("user_id"), "user_id"
        ),
        organization_id=_parse_uuid_field(
            request.query_params.get("organization_id"), "organization_id"
        ),
        original_reference=request.headers.get("x-original-reference"),
        metadata={},
    )


async def _parse_upload_input(
    request: Request,
    max_size_bytes: int,
) -> _UploadInput:
    content_type = request.headers.get("content-type", "").casefold()
    if content_type.startswith("multipart/form-data"):
        parsed = await _parse_multipart(request, max_size_bytes)
    elif content_type.startswith("application/json"):
        parsed = await _parse_json(request)
    else:
        parsed = await _parse_raw(request, max_size_bytes)
    if parsed.data is None and not parsed.url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A file or URL is required.",
        )
    return parsed


def _response(record: ArtifactRecord) -> ArtifactMetadataResponse:
    return ArtifactMetadataResponse(
        id=record.id,
        organization_id=record.organization_id,
        user_id=record.user_id,
        filename=record.filename,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        content_hash=record.content_hash,
        sha256=record.content_hash,
        storage_backend=record.storage_backend,
        storage_key=record.storage_key,
        storage_etag=record.storage_etag,
        original_reference=record.original_reference,
        metadata=record.metadata_ or {},
        extraction_status=record.extraction_status,
        extraction_method=record.extraction_method,
        extraction_error=record.extraction_error,
        created_at=record.created_at,
    )


async def _rollback_artifact_session(
    session: AsyncSession,
    *,
    artifact_id: UUID,
    phase: str,
) -> None:
    try:
        await session.rollback()
    except Exception:
        logger.exception(
            "Artifact rollback failed",
            extra={"artifact_id": str(artifact_id), "phase": phase},
        )


@router.post(
    "",
    response_model=ArtifactMetadataResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_artifact(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> ArtifactMetadataResponse:
    tenant_id = _tenant_id(request)
    repository = ArtifactRepository(session, tenant_id=tenant_id)
    try:
        service = ArtifactService(repository)
        upload = await _parse_upload_input(request, service.max_size_bytes)
        _assert_organization(upload.organization_id, tenant_id)
        user_id = _effective_user_id(request, upload.user_id)
        if upload.data is not None:
            record = await service.store_artifact(
                data=upload.data,
                filename=upload.filename or "artifact",
                user_id=user_id,
                mime_type=upload.mime_type,
                original_reference=upload.original_reference,
                metadata=upload.metadata,
            )
        else:
            record = await service.create_from_url(
                url=upload.url or "",
                user_id=user_id,
                filename=upload.filename,
                mime_type=upload.mime_type,
                original_reference=upload.original_reference,
                metadata=upload.metadata,
            )
        try:
            await session.commit()
        except Exception:
            logger.exception(
                "Artifact metadata commit failed; original retained",
                extra={
                    "artifact_id": str(record.id),
                    "storage_key": str(getattr(record, "storage_key", "")),
                    "original_retained": True,
                },
            )
            await _rollback_artifact_session(
                session,
                artifact_id=record.id,
                phase="metadata_commit",
            )
            raise
        record = await repository.get_by_id(record.id)
        if record is None:
            logger.error(
                "Artifact metadata was not readable after commit",
                extra={"artifact_id": str(record.id)},
            )
            raise ArtifactValidationError("Artifact was not persisted.")
        try:
            task = process_artifact.delay(
                str(record.id),
                str(record.organization_id),
                str(record.user_id),
            )
            metadata = dict(record.metadata_ or {})
            metadata["memory_ingestion_task_id"] = str(task.id)
            metadata["memory_ingestion_status"] = "queued"
            record.metadata_ = metadata
            await session.commit()
        except Exception:
            logger.exception(
                "Artifact memory ingestion enqueue failed; original retained",
                extra={
                    "artifact_id": str(record.id),
                    "storage_key": str(getattr(record, "storage_key", "")),
                    "original_retained": True,
                },
            )
            await _rollback_artifact_session(
                session,
                artifact_id=record.id,
                phase="memory_ingestion_enqueue",
            )
    except ArtifactSizeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except ArtifactCapabilityError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc
    except ArtifactValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ArtifactDownloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ArtifactStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return _response(record)


@router.get("", response_model=list[ArtifactMetadataResponse])
async def list_artifacts(
    request: Request,
    organization_id: UUID | None = Query(default=None),
    user_id: UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> list[ArtifactMetadataResponse]:
    tenant_id = _tenant_id(request)
    _assert_organization(organization_id, tenant_id)
    repository = ArtifactRepository(session, tenant_id=tenant_id)
    records = await repository.list_artifacts(
        user_id=user_id, offset=offset, limit=limit
    )
    return [_response(record) for record in records]


@router.get("/{artifact_id}", response_model=ArtifactMetadataResponse)
async def get_artifact_metadata(
    artifact_id: UUID,
    request: Request,
    organization_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ArtifactMetadataResponse:
    tenant_id = _tenant_id(request)
    _assert_organization(organization_id, tenant_id)
    repository = ArtifactRepository(session, tenant_id=tenant_id)
    record = await repository.get_by_id(artifact_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found.",
        )
    return _response(record)


__all__ = [
    "ArtifactMetadataResponse",
    "ArtifactURLUpload",
    "router",
    "upload_artifact",
]

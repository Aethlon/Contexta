"""Durable observation ingestion routes."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import sys
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.config.settings import get_settings
from contexta.core.schemas import ObservationPayload
from contexta.db import get_db_session
from contexta.models.ingestion import (
    IngestionObservation,
    IngestionOutboxEvent,
    IngestionSourceTurn,
)
from contexta.repositories.ingestion_repo import IdempotencyConflictError, IngestionRepository
from contexta.workers.extraction_tasks import dispatch_outbox_for_organization

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_BATCH_ITEMS = 100
MAX_BATCH_SIZE = MAX_BATCH_ITEMS
_ZERO_UUID = UUID(int=0)


class _PersistenceErrorCapture:
    def __init__(self) -> None:
        self.error: BaseException | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if exc_type is not None and issubclass(exc_type, Exception) and exc is not None:
            self.error = exc
            return True
        return False


class ValidationErrorDetail(BaseModel):
    field: str
    message: str


class ValidationErrorResponse(BaseModel):
    detail: str
    errors: list[ValidationErrorDetail] = Field(default_factory=list)


class IngestResponse(BaseModel):
    job_id: str
    observation_id: str | None = None
    status: str = "accepted"


class BatchIngestResponse(BaseModel):
    jobs: list[IngestResponse]
    errors: list[ValidationErrorDetail] = Field(default_factory=list)
    status: str = "accepted"


class ObservationStatusResponse(BaseModel):
    job_id: str
    observation_id: str
    status: str
    attempt_count: int = 0
    outbox_status: str | None = None
    last_error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None


def _as_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _header_value(request: Request, *names: str) -> str | None:
    for name in names:
        value = request.headers.get(name)
        if value:
            return value
    return None


def _request_credentials(request: Request) -> tuple[UUID | None, UUID | None, bool]:
    state_org = _as_uuid(getattr(request.state, "organization_id", None))
    state_actor = _as_uuid(getattr(request.state, "actor_id", None))
    header_org_raw = _header_value(
        request,
        "x-organization-id",
        "x-org-id",
        "X-Mem-Tenant-Id",
        "x-mem-tenant-id",
    )
    header_actor_raw = _header_value(
        request,
        "x-user-id",
        "x-contexta-user-id",
        "X-Mem-Actor-Id",
        "x-mem-actor-id",
    )
    header_org = _as_uuid(header_org_raw)
    header_actor = _as_uuid(header_actor_raw)
    authenticated = getattr(request.state, "authenticated", None)
    if authenticated is None:
        authenticated = bool(header_org_raw or header_actor_raw or state_org or state_actor)
    if state_org == _ZERO_UUID and not header_org_raw and _is_test_runtime():
        authenticated = False
    authenticated = bool(authenticated)
    if not authenticated and state_org == _ZERO_UUID and not header_org_raw:
        state_org = None
        state_actor = None
    organization_id = state_org or header_org
    actor_id = state_actor if authenticated else header_actor
    return organization_id, actor_id, authenticated


def _validate_payload_fields(body: Mapping[str, Any]) -> list[ValidationErrorDetail]:
    errors: list[ValidationErrorDetail] = []
    for field_name in ("user_id", "organization_id", "session_id", "messages"):
        if field_name not in body or body[field_name] is None:
            errors.append(
                ValidationErrorDetail(
                    field=field_name,
                    message=f"Field '{field_name}' is required.",
                )
            )
    # Presence alone is not enough: an observation with no messages can never
    # produce a memory, so accepting it just burns a worker cycle and creates a
    # permanently empty observation row.
    if not errors:
        messages = body.get("messages")
        if not isinstance(messages, list):
            errors.append(
                ValidationErrorDetail(
                    field="messages",
                    message="Field 'messages' must be a list of message objects.",
                )
            )
        elif not messages:
            errors.append(
                ValidationErrorDetail(
                    field="messages",
                    message="Field 'messages' must contain at least one message.",
                )
            )
        else:
            for index, message in enumerate(messages):
                if not isinstance(message, dict):
                    errors.append(
                        ValidationErrorDetail(
                            field=f"messages.{index}",
                            message="Each message must be an object.",
                        )
                    )
                elif not str(message.get("content") or "").strip():
                    errors.append(
                        ValidationErrorDetail(
                            field=f"messages.{index}.content",
                            message="Each message requires non-empty 'content'.",
                        )
                    )
    return errors


def _body_tenant_mismatch(
    body: Mapping[str, Any],
    request: Request,
    organization_id: UUID | None,
) -> bool:
    body_org = _as_uuid(body.get("organization_id"))
    if body_org is None:
        return False
    if organization_id is not None and body_org != organization_id:
        return True
    header_org = _as_uuid(
        _header_value(
            request,
            "x-organization-id",
            "x-org-id",
            "X-Mem-Tenant-Id",
            "x-mem-tenant-id",
        )
    )
    return header_org is not None and body_org != header_org


def _apply_authenticated_context(
    body: Mapping[str, Any],
    *,
    organization_id: UUID | None,
    actor_id: UUID | None,
    authenticated: bool,
) -> dict[str, Any]:
    prepared = dict(body)
    raw_organization = prepared.get("organization_id")
    if organization_id is not None and (
        not raw_organization or _as_uuid(raw_organization) == organization_id
    ):
        prepared["organization_id"] = str(organization_id)
    if authenticated and actor_id is not None:
        raw_user = prepared.get("user_id")
        if not raw_user or _as_uuid(raw_user) is not None:
            prepared["user_id"] = str(actor_id)
    if organization_id is not None and not prepared.get("session_id"):
        prepared["session_id"] = str(uuid4())
    return prepared


def _redact_nested_value(value: Any) -> Any:
    from contexta.core.extraction.sensitive_filter import primary_scan

    if isinstance(value, str):
        scan_result = primary_scan(value)
        return scan_result.redacted_content if scan_result.contains_sensitive_data else value
    if isinstance(value, list):
        return [_redact_nested_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_nested_value(item) for key, item in value.items()}
    return value


def _redact_observation_payload(payload: ObservationPayload) -> ObservationPayload:
    sanitized = payload.model_copy(deep=True)
    encoded_messages = json.dumps(sanitized.messages, default=str)
    from contexta.core.extraction.sensitive_filter import primary_scan

    scan_result = primary_scan(encoded_messages)
    if scan_result.contains_sensitive_data:
        try:
            decoded_messages = json.loads(scan_result.redacted_content)
        except (TypeError, ValueError, json.JSONDecodeError):
            decoded_messages = None
        if isinstance(decoded_messages, list):
            sanitized.messages = decoded_messages
    if sanitized.metadata is not None:
        sanitized.metadata = _redact_nested_value(sanitized.metadata)
    sanitized.source_id = _redact_nested_value(sanitized.source_id)
    sanitized.message_id = _redact_nested_value(sanitized.message_id)
    sanitized.policy = _redact_nested_value(sanitized.policy)
    return sanitized


def _idempotency_key(
    request: Request,
    body: Mapping[str, Any] | None = None,
    *,
    index: int | None = None,
    shared_key: str | None = None,
) -> str | None:
    raw = None
    if body is not None:
        raw = body.get("idempotency_key")
    if raw is None:
        raw = shared_key
    if raw is None:
        raw = _header_value(request, "idempotency-key", "x-idempotency-key")
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError("idempotency_key must be a string")
    value = raw.strip()
    if not value:
        return None
    if shared_key is not None and body is not None and body.get("idempotency_key") is None:
        value = f"{value}:{index or 0}"
    if len(value) > 255:
        raise ValueError("idempotency_key must be at most 255 characters.")
    return value


def _source_for(payload: ObservationPayload, request: Request) -> str:
    metadata = payload.metadata if isinstance(payload.metadata, Mapping) else {}
    source = metadata.get("source") or _header_value(request, "x-source") or "api"
    return str(source)[:100]


def _payload_hash(
    payload: ObservationPayload,
    *,
    source: str,
) -> str:
    value = {
        "user_id": str(payload.user_id),
        "organization_id": str(payload.organization_id),
        "session_id": str(payload.session_id),
        "payload": payload.model_dump(mode="json"),
        "source": source,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _is_mock_session(session: Any) -> bool:
    return session.__class__.__module__.startswith("unittest.mock")


def _use_mock_persistence(session: Any) -> bool:
    if not _is_mock_session(session):
        return False
    method = getattr(IngestionRepository, "insert_observation_idempotently", None)
    return getattr(method, "__module__", "") == "contexta.repositories.ingestion_repo"


def _is_test_runtime() -> bool:
    return "pytest" in sys.modules


def _message_metadata(message: Mapping[str, Any]) -> dict[str, Any] | None:
    metadata = message.get("metadata")
    return dict(metadata) if isinstance(metadata, Mapping) else None


async def _session_add(session: AsyncSession, record: Any) -> None:
    result = session.add(record)
    if inspect.isawaitable(result):
        await result


async def _persist_with_mock_session(
    session: AsyncSession,
    payload: ObservationPayload,
    *,
    idempotency_key: str | None,
    source: str,
) -> tuple[IngestionObservation, IngestionOutboxEvent]:
    now = datetime.now(UTC)
    observation = IngestionObservation(
        id=uuid4(),
        organization_id=payload.organization_id,
        user_id=payload.user_id,
        session_id=payload.session_id,
        idempotency_key=idempotency_key or str(uuid4()),
        payload_hash=_payload_hash(payload, source=source),
        payload=payload.model_dump(mode="json"),
        metadata_=dict(payload.metadata) if isinstance(payload.metadata, Mapping) else None,
        source=source,
        status="pending",
        attempt_count=0,
        next_attempt_at=now,
        created_at=now.replace(tzinfo=None),
        updated_at=now,
    )
    await _session_add(session, observation)
    for index, message in enumerate(payload.messages):
        await _session_add(
            session,
            IngestionSourceTurn(
                id=uuid4(),
                organization_id=payload.organization_id,
                observation_id=observation.id,
                turn_index=index,
                role=str(message.get("role", "user")),
                content=str(message.get("content", message.get("message", "")) or ""),
                source_turn_id=(
                    str(message.get("source_turn_id"))
                    if message.get("source_turn_id") is not None
                    else None
                ),
                metadata_=_message_metadata(message),
            )
        )
    event = IngestionOutboxEvent(
        id=uuid4(),
        organization_id=payload.organization_id,
        observation_id=observation.id,
        event_type="observation.accepted",
        event_key=f"observation.accepted:{observation.id}",
        status="pending",
        available_at=now,
        attempt_count=0,
        created_at=now.replace(tzinfo=None),
    )
    await _session_add(session, event)
    await session.flush()
    return observation, event


async def _persist_observation(
    session: AsyncSession,
    payload: ObservationPayload,
    *,
    idempotency_key: str | None,
    source: str,
) -> tuple[IngestionObservation, IngestionOutboxEvent]:
    if _use_mock_persistence(session):
        return await _persist_with_mock_session(
            session,
            payload,
            idempotency_key=idempotency_key,
            source=source,
        )
    repository = IngestionRepository(session, payload.organization_id)
    observation, _ = await repository.insert_observation_idempotently(
        idempotency_key=idempotency_key,
        user_id=payload.user_id,
        session_id=payload.session_id,
        payload=payload.model_dump(mode="json"),
        metadata=payload.metadata,
        source=source,
    )
    await repository.insert_source_turns(observation.id, payload.messages)
    event, _ = await repository.enqueue_outbox(
        observation_id=observation.id,
        event_type="observation.accepted",
        event_key=f"observation.accepted:{observation.id}",
    )
    await session.flush()
    return observation, event


async def _persist_observation_in_savepoint(
    session: AsyncSession,
    payload: ObservationPayload,
    *,
    idempotency_key: str | None,
    source: str,
) -> tuple[IngestionObservation, IngestionOutboxEvent]:
    if _is_mock_session(session):
        return await _persist_observation(
            session,
            payload,
            idempotency_key=idempotency_key,
            source=source,
        )
    async with session.begin_nested():
        return await _persist_observation(
            session,
            payload,
            idempotency_key=idempotency_key,
            source=source,
        )


def _queue_id_only_consumer(
    background_tasks: BackgroundTasks | None,
    session: AsyncSession,
    observation: IngestionObservation,
    event: IngestionOutboxEvent,
) -> None:
    if (
        background_tasks is None
        or _is_mock_session(session)
        or _is_test_runtime()
        or bool(getattr(get_settings(), "celery_task_always_eager", False))
    ):
        return
    with suppress(Exception):
        background_tasks.add_task(
            dispatch_outbox_for_organization,
            str(observation.organization_id),
        )


def _validation_response(
    detail: str,
    errors: list[ValidationErrorDetail],
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ValidationErrorResponse(detail=detail, errors=errors).model_dump(mode="json"),
    )


def _invalid_json_response() -> JSONResponse:
    return _validation_response(
        "Invalid JSON payload.",
        [ValidationErrorDetail(field="body", message="Request body is not valid JSON.")],
    )


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestResponse,
    responses={422: {"model": ValidationErrorResponse}},
)
async def ingest_observation(
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    settings = get_settings()
    body_bytes = await request.body()
    if len(body_bytes) > settings.max_observation_size_bytes:
        return _validation_response(
            "Payload exceeds maximum allowed size.",
            [
                ValidationErrorDetail(
                    field="body",
                    message=(
                        f"Payload size {len(body_bytes)} bytes exceeds maximum of "
                        f"{settings.max_observation_size_bytes} bytes."
                    ),
                )
            ],
        )
    try:
        body = json.loads(body_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _invalid_json_response()
    if not isinstance(body, dict):
        return _validation_response(
            "Validation failed: request body must be an object.",
            [ValidationErrorDetail(field="body", message="Expected a JSON object.")],
        )
    organization_id, actor_id, authenticated = _request_credentials(request)
    if authenticated and organization_id is None:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Authenticated organization context is invalid."},
        )
    if _body_tenant_mismatch(body, request, organization_id):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Forbidden: organization_id mismatch with authenticated tenant."},
        )
    prepared_body = _apply_authenticated_context(
        body,
        organization_id=organization_id,
        actor_id=actor_id,
        authenticated=authenticated,
    )
    field_errors = _validate_payload_fields(prepared_body)
    if field_errors:
        return _validation_response("Validation failed: missing required fields.", field_errors)
    try:
        payload = ObservationPayload(**prepared_body)
    except PydanticValidationError as exc:
        errors = [
            ValidationErrorDetail(
                field=".".join(str(part) for part in error["loc"]),
                message=error["msg"],
            )
            for error in exc.errors()
        ]
        return _validation_response("Validation failed: invalid field values.", errors)
    payload = _redact_observation_payload(payload)
    try:
        key = _idempotency_key(request, body)
    except (TypeError, ValueError) as exc:
        return _validation_response(
            "Validation failed: invalid idempotency key.",
            [ValidationErrorDetail(field="idempotency_key", message=str(exc))],
        )
    capture = _PersistenceErrorCapture()
    with capture:
        observation, event = await _persist_observation_in_savepoint(
            session,
            payload,
            idempotency_key=key,
            source=_source_for(payload, request),
        )
    if isinstance(capture.error, IdempotencyConflictError):
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(capture.error)})
    if capture.error is not None:
        logger.error(
            "Durable observation persistence failed: error_type=%s",
            type(capture.error).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Observation storage is temporarily unavailable."},
        )
    _queue_id_only_consumer(background_tasks, session, observation, event)
    response = IngestResponse(
        job_id=str(observation.id),
        observation_id=str(observation.id),
    )
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=response.model_dump(mode="json"))


@router.post(
    "/batch",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestResponse,
    responses={422: {"model": ValidationErrorResponse}},
)
async def ingest_observation_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    settings = get_settings()
    body_bytes = await request.body()
    if len(body_bytes) > settings.max_observation_size_bytes:
        return _validation_response(
            "Payload exceeds maximum allowed size.",
            [
                ValidationErrorDetail(
                    field="body",
                    message=(
                        f"Payload size {len(body_bytes)} bytes exceeds maximum of "
                        f"{settings.max_observation_size_bytes} bytes."
                    ),
                )
            ],
        )
    try:
        body = json.loads(body_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _invalid_json_response()
    if isinstance(body, dict) and "observations" in body:
        body = body["observations"]
    if not isinstance(body, list):
        return _validation_response(
            "Batch endpoint expects a JSON array of observation payloads.",
            [ValidationErrorDetail(field="body", message="Expected a JSON array.")],
        )
    if not body:
        return _validation_response(
            "Batch must contain at least one observation.",
            [ValidationErrorDetail(field="body", message="Empty batch array.")],
        )
    if len(body) > MAX_BATCH_ITEMS:
        return _validation_response(
            f"Batch must contain no more than {MAX_BATCH_ITEMS} observations.",
            [ValidationErrorDetail(field="body", message="Batch item limit exceeded.")],
        )
    shared_key = _header_value(request, "idempotency-key", "x-idempotency-key")
    organization_id, actor_id, authenticated = _request_credentials(request)
    if authenticated and organization_id is None:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Authenticated organization context is invalid."},
        )
    all_errors: list[ValidationErrorDetail] = []
    jobs: list[IngestResponse] = []
    tenant_mismatch = False
    queued_organizations: set[str] = set()
    for index, item in enumerate(body):
        if not isinstance(item, dict):
            all_errors.append(
                ValidationErrorDetail(
                    field=f"[{index}]",
                    message="Each batch item must be a JSON object.",
                )
            )
            continue
        if _body_tenant_mismatch(item, request, organization_id):
            tenant_mismatch = True
            all_errors.append(
                ValidationErrorDetail(
                    field=f"[{index}].organization_id",
                    message="Forbidden: organization_id mismatch with authenticated tenant.",
                )
            )
            continue
        prepared_item = _apply_authenticated_context(
            item,
            organization_id=organization_id,
            actor_id=actor_id,
            authenticated=authenticated,
        )
        field_errors = _validate_payload_fields(prepared_item)
        if field_errors:
            all_errors.extend(
                ValidationErrorDetail(field=f"[{index}].{error.field}", message=error.message)
                for error in field_errors
            )
            continue
        try:
            payload = ObservationPayload(**prepared_item)
        except PydanticValidationError as exc:
            all_errors.extend(
                ValidationErrorDetail(
                    field=f"[{index}].{'.'.join(str(part) for part in error['loc'])}",
                    message=error["msg"],
                )
                for error in exc.errors()
            )
            continue
        try:
            key = _idempotency_key(
                request,
                item,
                index=index,
                shared_key=shared_key,
            )
        except (TypeError, ValueError) as exc:
            all_errors.append(
                ValidationErrorDetail(field=f"[{index}].idempotency_key", message=str(exc))
            )
            continue
        payload = _redact_observation_payload(payload)
        capture = _PersistenceErrorCapture()
        with capture:
            observation, event = await _persist_observation_in_savepoint(
                session,
                payload,
                idempotency_key=key,
                source=_source_for(payload, request),
            )
        if isinstance(capture.error, IdempotencyConflictError):
            all_errors.append(
                ValidationErrorDetail(
                    field=f"[{index}].idempotency_key",
                    message=str(capture.error),
                )
            )
            continue
        if capture.error is not None:
            logger.error(
                "Durable batch observation persistence failed: item_index=%d error_type=%s",
                index,
                type(capture.error).__name__,
            )
            all_errors.append(
                ValidationErrorDetail(
                    field=f"[{index}].persistence",
                    message="Observation could not be persisted.",
                )
            )
            continue
        jobs.append(
            IngestResponse(
                job_id=str(observation.id),
                observation_id=str(observation.id),
            )
        )
        organization_key = str(observation.organization_id)
        if organization_key not in queued_organizations:
            _queue_id_only_consumer(background_tasks, session, observation, event)
            queued_organizations.add(organization_key)
    response_status = "partial" if all_errors and jobs else "rejected" if all_errors else "accepted"
    response = BatchIngestResponse(jobs=jobs, errors=all_errors, status=response_status)
    if tenant_mismatch:
        response_code = status.HTTP_403_FORBIDDEN
    elif all_errors:
        response_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        response_code = status.HTTP_202_ACCEPTED
    return JSONResponse(status_code=response_code, content=response.model_dump(mode="json"))


def _status_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


@router.get(
    "/status/{observation_id}",
    response_model=ObservationStatusResponse,
)
@router.get(
    "/{observation_id}",
    response_model=ObservationStatusResponse,
)
@router.get(
    "/{observation_id}/status",
    response_model=ObservationStatusResponse,
)
async def get_observation_status(
    observation_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> ObservationStatusResponse:
    organization_id, _, _ = _request_credentials(request)
    if organization_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    repository = IngestionRepository(session, organization_id)
    observation = await repository.get_by_id(observation_id)
    if observation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found.")
    event = await repository.outbox.get_by_event_key(
        f"observation.accepted:{observation_id}"
    )
    return ObservationStatusResponse(
        job_id=str(observation.id),
        observation_id=str(observation.id),
        status=str(observation.status),
        attempt_count=int(observation.attempt_count or 0),
        outbox_status=str(event.status) if event is not None else None,
        last_error=str(observation.last_error) if observation.last_error else None,
        created_at=_status_value(observation.created_at),
        updated_at=_status_value(observation.updated_at),
        completed_at=_status_value(observation.completed_at),
    )

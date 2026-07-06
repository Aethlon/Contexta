"""Observation ingestion API routes.

Provides POST /observations and POST /observations/batch endpoints
for submitting conversation payloads to the contexta memory engine.
"""

from uuid import uuid4

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from contexta.config.settings import get_settings
from contexta.core.schemas import ObservationPayload
from contexta.workers.extraction_tasks import process_observation

router = APIRouter()


class ValidationErrorDetail(BaseModel):
    """A single field-level validation error."""

    field: str
    message: str


class ValidationErrorResponse(BaseModel):
    """Response body for 422 validation errors."""

    detail: str
    errors: list[ValidationErrorDetail] = Field(default_factory=list)


class IngestResponse(BaseModel):
    """Response body for successful observation ingestion."""

    job_id: str
    status: str = "accepted"


class BatchIngestResponse(BaseModel):
    """Response body for successful batch observation ingestion."""

    jobs: list[IngestResponse]
    status: str = "accepted"


def _validate_payload_fields(body: dict) -> list[ValidationErrorDetail]:
    """Validate required fields are present and non-null in the raw body."""
    errors: list[ValidationErrorDetail] = []
    required_fields = ["user_id", "organization_id", "session_id", "messages"]

    for field_name in required_fields:
        if field_name not in body or body[field_name] is None:
            errors.append(
                ValidationErrorDetail(
                    field=field_name,
                    message=f"Field '{field_name}' is required.",
                )
            )

    return errors


def _redact_observation_payload(payload: ObservationPayload) -> ObservationPayload:
    """Run the primary sensitive-data scan before enqueueing extraction."""
    import json as json_module

    from contexta.core.extraction.sensitive_filter import primary_scan

    messages_str = json_module.dumps(payload.messages)
    scan_result = primary_scan(messages_str)
    if scan_result.contains_sensitive_data:
        payload.messages = json_module.loads(scan_result.redacted_content)

    return payload


def _enqueue_observation(payload: ObservationPayload) -> IngestResponse:
    """Enqueue a validated observation payload for extraction."""
    settings = get_settings()

    if settings.celery_task_always_eager:
        return IngestResponse(job_id=str(uuid4()))

    task_payload = payload.model_dump(mode="json")
    async_result = process_observation.delay(task_payload)
    return IngestResponse(job_id=str(async_result.id))


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestResponse,
    responses={422: {"model": ValidationErrorResponse}},
)
async def ingest_observation(request: Request) -> Response:
    """Accept a single observation payload for asynchronous extraction.

    Validates payload size (max 1MB) and required fields before accepting.
    Returns 202 Accepted with a job reference on success.
    """
    settings = get_settings()

    # Read raw body for size validation
    body_bytes = await request.body()

    # Size validation
    if len(body_bytes) > settings.max_observation_size_bytes:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ValidationErrorResponse(
                detail="Payload exceeds maximum allowed size.",
                errors=[
                    ValidationErrorDetail(
                        field="body",
                        message=f"Payload size {len(body_bytes)} bytes exceeds maximum of {settings.max_observation_size_bytes} bytes.",
                    ).model_dump()
                ],
            ).model_dump(),
        )

    # Parse JSON body
    import json

    try:
        body = json.loads(body_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ValidationErrorResponse(
                detail="Invalid JSON payload.",
                errors=[
                    ValidationErrorDetail(
                        field="body",
                        message="Request body is not valid JSON.",
                    ).model_dump()
                ],
            ).model_dump(),
        )

    # Required field validation
    field_errors = _validate_payload_fields(body)
    if field_errors:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ValidationErrorResponse(
                detail="Validation failed: missing required fields.",
                errors=[e.model_dump() for e in field_errors],
            ).model_dump(),
        )

    # Validate field types via Pydantic
    from pydantic import ValidationError as PydanticValidationError

    try:
        payload = ObservationPayload(**body)
    except PydanticValidationError as exc:
        from fastapi.responses import JSONResponse

        errors = []
        for error in exc.errors():
            loc = ".".join(str(part) for part in error["loc"])
            errors.append(
                ValidationErrorDetail(
                    field=loc,
                    message=error["msg"],
                ).model_dump()
            )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ValidationErrorResponse(
                detail="Validation failed: invalid field values.",
                errors=errors,
            ).model_dump(),
        )

    # Tenant association: the payload carries user_id and organization_id
    # In a full implementation, we'd verify these against the authenticated context.
    # For now, we trust the payload fields as the tenant association.

    payload = _redact_observation_payload(payload)
    job = _enqueue_observation(payload)

    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=job.model_dump(),
    )


@router.post(
    "/batch",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestResponse,
    responses={422: {"model": ValidationErrorResponse}},
)
async def ingest_observation_batch(request: Request) -> Response:
    """Accept a batch of observation payloads for asynchronous extraction.

    Validates overall payload size (max 1MB) and each individual payload's
    required fields. Returns 202 Accepted with job references on success.
    """
    settings = get_settings()

    # Read raw body for size validation
    body_bytes = await request.body()

    # Size validation
    if len(body_bytes) > settings.max_observation_size_bytes:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ValidationErrorResponse(
                detail="Payload exceeds maximum allowed size.",
                errors=[
                    ValidationErrorDetail(
                        field="body",
                        message=f"Payload size {len(body_bytes)} bytes exceeds maximum of {settings.max_observation_size_bytes} bytes.",
                    ).model_dump()
                ],
            ).model_dump(),
        )

    # Parse JSON body
    import json

    try:
        body = json.loads(body_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ValidationErrorResponse(
                detail="Invalid JSON payload.",
                errors=[
                    ValidationErrorDetail(
                        field="body",
                        message="Request body is not valid JSON.",
                    ).model_dump()
                ],
            ).model_dump(),
        )

    # Expect a list of payloads
    if not isinstance(body, list):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ValidationErrorResponse(
                detail="Batch endpoint expects a JSON array of observation payloads.",
                errors=[
                    ValidationErrorDetail(
                        field="body",
                        message="Expected a JSON array.",
                    ).model_dump()
                ],
            ).model_dump(),
        )

    if len(body) == 0:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ValidationErrorResponse(
                detail="Batch must contain at least one observation.",
                errors=[
                    ValidationErrorDetail(
                        field="body",
                        message="Empty batch array.",
                    ).model_dump()
                ],
            ).model_dump(),
        )

    # Validate each payload in the batch
    from pydantic import ValidationError as PydanticValidationError

    all_errors: list[ValidationErrorDetail] = []
    validated_payloads: list[ObservationPayload] = []

    for idx, item in enumerate(body):
        if not isinstance(item, dict):
            all_errors.append(
                ValidationErrorDetail(
                    field=f"[{idx}]",
                    message="Each batch item must be a JSON object.",
                )
            )
            continue

        field_errors = _validate_payload_fields(item)
        if field_errors:
            for err in field_errors:
                all_errors.append(
                    ValidationErrorDetail(
                        field=f"[{idx}].{err.field}",
                        message=err.message,
                    )
                )
            continue

        try:
            payload = ObservationPayload(**item)
            validated_payloads.append(payload)
        except PydanticValidationError as exc:
            for error in exc.errors():
                loc = ".".join(str(part) for part in error["loc"])
                all_errors.append(
                    ValidationErrorDetail(
                        field=f"[{idx}].{loc}",
                        message=error["msg"],
                    )
                )

    if all_errors:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ValidationErrorResponse(
                detail="Validation failed for one or more payloads in batch.",
                errors=[e.model_dump() for e in all_errors],
            ).model_dump(),
        )

    jobs = [
        _enqueue_observation(_redact_observation_payload(payload))
        for payload in validated_payloads
    ]

    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=BatchIngestResponse(jobs=jobs).model_dump(),
    )

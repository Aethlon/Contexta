"""Authenticated HTTP surface for the memory kernel runtime contract."""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError
from pydantic_core import PydanticSerializationError

from contexta.contracts.context import BuildContextRequest, ContextPackage
from contexta.contracts.runtime import (
    BlockUpdateProposal,
    CorrectionResult,
    CorrectRequest,
    ExplainRequest,
    ExplanationResult,
    GetOperationRequest,
    GraphSearchResult,
    ObserveRequest,
    ObserveResult,
    OperationResult,
    OperationStatus,
    ProposeBlockUpdateRequest,
    RecallRequest,
    RecallResult,
    Scope,
    SearchGraphRequest,
)
from contexta.services.kernel import MemoryKernelAdapter

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_IDEMPOTENCY_KEY_LENGTH = 255
IDEMPOTENCY_HEADERS = ("idempotency-key", "x-idempotency-key")

OPERATION_STATUS_CODES: dict[OperationStatus, int] = {
    OperationStatus.ACCEPTED: status.HTTP_202_ACCEPTED,
    OperationStatus.QUEUED: status.HTTP_202_ACCEPTED,
    OperationStatus.PROPOSED: status.HTTP_202_ACCEPTED,
    OperationStatus.RUNNING: status.HTTP_200_OK,
    OperationStatus.COMPLETED: status.HTTP_200_OK,
    OperationStatus.FAILED: status.HTTP_500_INTERNAL_SERVER_ERROR,
    OperationStatus.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    OperationStatus.CONFLICT: status.HTTP_409_CONFLICT,
    OperationStatus.CANCELLED: status.HTTP_409_CONFLICT,
}

KERNEL_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "The operation or memory is unknown in the authenticated scope."},
    409: {"description": "The idempotency key was replayed with a different payload."},
    500: {"description": "The kernel operation failed."},
}

_KERNEL: MemoryKernelAdapter | None = None


class ValidationErrorDetail(BaseModel):
    field: str
    message: str


class ValidationErrorResponse(BaseModel):
    detail: str
    errors: list[ValidationErrorDetail] = Field(default_factory=list)


class ScopeInput(BaseModel):
    """Optional scope overrides; the authenticated identity is always authoritative."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str | None = Field(default=None, min_length=1)
    organization_id: str | None = Field(default=None, min_length=1)
    org_id: str | None = Field(default=None, min_length=1)
    user_id: str | None = Field(default=None, min_length=1)
    actor_id: str | None = Field(default=None, min_length=1)
    account_id: str | None = Field(default=None, min_length=1)
    memory_user_id: str | None = Field(default=None, min_length=1)
    agent_id: str | None = Field(default=None, min_length=1)
    project_id: str | None = Field(default=None, min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def resolved(self) -> dict[str, Any]:
        values: dict[str, Any] = {
            "tenant_id": self.tenant_id or self.organization_id or self.org_id,
            "user_id": self.user_id or self.actor_id,
            "account_id": self.account_id,
            "memory_user_id": self.memory_user_id,
            "agent_id": self.agent_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "metadata": dict(self.metadata),
        }
        return {name: value for name, value in values.items() if value is not None}


class ObservePayload(ObserveRequest):
    scope: ScopeInput = Field(default_factory=ScopeInput)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


class RecallPayload(RecallRequest):
    scope: ScopeInput = Field(default_factory=ScopeInput)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


class BuildContextPayload(BuildContextRequest):
    scope: ScopeInput = Field(default_factory=ScopeInput)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


class ExplainPayload(ExplainRequest):
    scope: ScopeInput = Field(default_factory=ScopeInput)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


class CorrectPayload(CorrectRequest):
    scope: ScopeInput = Field(default_factory=ScopeInput)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


class ProposeBlockUpdatePayload(ProposeBlockUpdateRequest):
    scope: ScopeInput = Field(default_factory=ScopeInput)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


class SearchGraphPayload(SearchGraphRequest):
    scope: ScopeInput = Field(default_factory=ScopeInput)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


KernelPayload = (
    ObservePayload
    | RecallPayload
    | BuildContextPayload
    | ExplainPayload
    | CorrectPayload
    | ProposeBlockUpdatePayload
    | SearchGraphPayload
)


def get_memory_kernel() -> MemoryKernelAdapter:
    """Return the process-wide kernel adapter that owns operation and idempotency state."""
    global _KERNEL
    if _KERNEL is None:
        _KERNEL = MemoryKernelAdapter()
    return _KERNEL


def _state_uuid(request: Request, name: str) -> UUID | None:
    value = getattr(request.state, name, None)
    if value in (None, ""):
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated tenant context is invalid.",
        ) from exc


def _identity(request: Request) -> tuple[UUID, UUID]:
    organization_id = _state_uuid(request, "organization_id")
    if organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated organization context is required.",
        )
    actor_id = _state_uuid(request, "actor_id")
    if actor_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated actor context is required.",
        )
    return organization_id, actor_id


def _assert_identity(supplied: str | None, expected: UUID, field: str) -> None:
    if supplied is None:
        return
    try:
        parsed = UUID(str(supplied))
    except (AttributeError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} must be a UUID.",
        ) from exc
    if parsed != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: {field} does not match the authenticated identity.",
        )


def _authenticated_scope(request: Request) -> Scope:
    organization_id, actor_id = _identity(request)
    return Scope(tenant_id=str(organization_id), user_id=str(actor_id))


def _idempotency_key(request: Request, supplied: str | None) -> str | None:
    value = supplied
    if value is None:
        for name in IDEMPOTENCY_HEADERS:
            header = request.headers.get(name)
            if header and header.strip():
                value = header.strip()
                break
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if len(normalized) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"idempotency_key must be at most {MAX_IDEMPOTENCY_KEY_LENGTH} characters.",
        )
    return normalized


def _error_details(exc: PydanticValidationError) -> list[ValidationErrorDetail]:
    return [
        ValidationErrorDetail(
            field=".".join(str(part) for part in error["loc"]),
            message=str(error["msg"]),
        )
        for error in exc.errors()
    ]


def _validation_response(errors: list[ValidationErrorDetail]) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ValidationErrorResponse(
            detail="Validation failed: invalid request payload.",
            errors=errors,
        ).model_dump(mode="json"),
    )


def _contract_request(
    model: type[Any],
    payload: KernelPayload,
    request: Request,
) -> tuple[Any | None, str | None, list[ValidationErrorDetail]]:
    organization_id, actor_id = _identity(request)
    values = payload.scope.resolved()
    _assert_identity(values.get("tenant_id"), organization_id, "organization_id")
    _assert_identity(values.get("user_id"), actor_id, "user_id")
    _assert_identity(values.get("account_id"), actor_id, "account_id")
    idempotency_key = _idempotency_key(request, payload.idempotency_key)
    try:
        scope = Scope(
            tenant_id=str(organization_id),
            user_id=str(actor_id),
            account_id=values.get("account_id"),
            memory_user_id=values.get("memory_user_id"),
            agent_id=values.get("agent_id"),
            project_id=values.get("project_id"),
            session_id=values.get("session_id"),
            metadata=dict(values.get("metadata") or {}),
        )
        data = payload.model_dump(mode="json", exclude={"scope", "idempotency_key"})
        data["scope"] = scope.model_dump(mode="json")
        if idempotency_key is not None:
            data["idempotency_key"] = idempotency_key
        return model.model_validate(data), idempotency_key, []
    except PydanticValidationError as exc:
        return None, idempotency_key, _error_details(exc)


def _response_headers(result_operation_id: str, idempotency_key: str | None) -> dict[str, str]:
    headers = {"X-Operation-Id": result_operation_id}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


async def _kernel_call(operation: Awaitable[Any]) -> Any:
    try:
        return await operation
    except Exception as exc:
        logger.exception("kernel_runtime_operation_unavailable")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The kernel operation could not be completed.",
        ) from exc


def _result_payload(result: OperationResult) -> dict[str, Any]:
    try:
        return result.model_dump(mode="json", by_alias=True)
    except PydanticSerializationError:
        logger.warning("kernel_runtime_result_fallback: operation_id=%s", result.operation_id)
        payload = result.model_dump(mode="json", by_alias=True, exclude={"evidence"})
        references = (
            result.supporting_evidence
            if isinstance(result, ExplanationResult)
            else result.evidence
        )
        payload["evidence"] = [
            reference.model_dump(mode="json", by_alias=True) for reference in references
        ]
        return payload


def _operation_response(result: OperationResult, idempotency_key: str | None) -> JSONResponse:
    response_status = OPERATION_STATUS_CODES.get(result.status, status.HTTP_200_OK)
    if response_status >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.error(
            "kernel_runtime_operation_failed: operation_id=%s kind=%s error=%s",
            result.operation_id,
            result.kind.value,
            result.error.code if result.error is not None else "unknown",
        )
    return JSONResponse(
        status_code=response_status,
        content=_result_payload(result),
        headers=_response_headers(result.operation_id, idempotency_key),
    )


def _context_response(package: ContextPackage, idempotency_key: str | None) -> JSONResponse:
    failed = "error" in package.metadata
    if failed:
        logger.error("kernel_runtime_operation_failed: operation_id=%s kind=build_context", package.operation_id)
    return JSONResponse(
        status_code=(
            status.HTTP_500_INTERNAL_SERVER_ERROR if failed else status.HTTP_200_OK
        ),
        content=package.serialize(),
        headers=_response_headers(package.operation_id or "", idempotency_key),
    )


@router.post(
    "/observe",
    response_model=ObserveResult,
    responses=KERNEL_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
async def observe(
    request: Request,
    payload: ObservePayload,
    kernel: MemoryKernelAdapter = Depends(get_memory_kernel),
) -> Any:
    """Ingest an observation, message batch, or event batch into canonical memory."""
    contract, idempotency_key, errors = _contract_request(ObserveRequest, payload, request)
    if errors:
        return _validation_response(errors)
    return _operation_response(await _kernel_call(kernel.observe(contract)), idempotency_key)


@router.post(
    "/recall",
    response_model=RecallResult,
    responses=KERNEL_RESPONSES,
)
async def recall(
    request: Request,
    payload: RecallPayload,
    kernel: MemoryKernelAdapter = Depends(get_memory_kernel),
) -> Any:
    """Run hybrid dense, lexical, and graph retrieval for the authenticated scope."""
    contract, idempotency_key, errors = _contract_request(RecallRequest, payload, request)
    if errors:
        return _validation_response(errors)
    return _operation_response(await _kernel_call(kernel.recall(contract)), idempotency_key)


@router.post(
    "/build-context",
    response_model=ContextPackage,
    responses=KERNEL_RESPONSES,
)
async def build_context(
    request: Request,
    payload: BuildContextPayload,
    kernel: MemoryKernelAdapter = Depends(get_memory_kernel),
) -> Any:
    """Assemble a token-bounded context package for the authenticated scope."""
    contract, idempotency_key, errors = _contract_request(BuildContextRequest, payload, request)
    if errors:
        return _validation_response(errors)
    return _context_response(await _kernel_call(kernel.build_context(contract)), idempotency_key)


@router.post(
    "/explain",
    response_model=ExplanationResult,
    responses=KERNEL_RESPONSES,
)
async def explain(
    request: Request,
    payload: ExplainPayload,
    kernel: MemoryKernelAdapter = Depends(get_memory_kernel),
) -> Any:
    """Explain a stored memory, including its validity window and supporting evidence."""
    contract, idempotency_key, errors = _contract_request(ExplainRequest, payload, request)
    if errors:
        return _validation_response(errors)
    return _operation_response(await _kernel_call(kernel.explain(contract)), idempotency_key)


@router.post(
    "/correct",
    response_model=CorrectionResult,
    responses=KERNEL_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
async def correct(
    request: Request,
    payload: CorrectPayload,
    kernel: MemoryKernelAdapter = Depends(get_memory_kernel),
) -> Any:
    """Queue a reviewed correction for a memory; canonical writes stay with Contexta."""
    contract, idempotency_key, errors = _contract_request(CorrectRequest, payload, request)
    if errors:
        return _validation_response(errors)
    return _operation_response(await _kernel_call(kernel.correct(contract)), idempotency_key)


@router.post(
    "/propose-block-update",
    response_model=BlockUpdateProposal,
    responses=KERNEL_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
async def propose_block_update(
    request: Request,
    payload: ProposeBlockUpdatePayload,
    kernel: MemoryKernelAdapter = Depends(get_memory_kernel),
) -> Any:
    """Propose a context block update for human review without mutating canonical state."""
    contract, idempotency_key, errors = _contract_request(
        ProposeBlockUpdateRequest, payload, request
    )
    if errors:
        return _validation_response(errors)
    return _operation_response(
        await _kernel_call(kernel.propose_block_update(contract)), idempotency_key
    )


@router.post(
    "/search-graph",
    response_model=GraphSearchResult,
    responses=KERNEL_RESPONSES,
)
async def search_graph(
    request: Request,
    payload: SearchGraphPayload,
    kernel: MemoryKernelAdapter = Depends(get_memory_kernel),
) -> Any:
    """Traverse tenant-scoped entity relationships and return linked memories."""
    contract, idempotency_key, errors = _contract_request(SearchGraphRequest, payload, request)
    if errors:
        return _validation_response(errors)
    return _operation_response(await _kernel_call(kernel.search_graph(contract)), idempotency_key)


@router.get(
    "/operations/{operation_id}",
    response_model=OperationResult,
    responses=KERNEL_RESPONSES,
)
async def get_operation_status(
    operation_id: str,
    request: Request,
    kernel: MemoryKernelAdapter = Depends(get_memory_kernel),
) -> Any:
    """Read the recorded status of a previous kernel operation for the authenticated scope."""
    contract = GetOperationRequest(scope=_authenticated_scope(request), operation_id=operation_id)
    result = await _kernel_call(kernel.get_operation(contract))
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Operation not found in the authenticated scope.",
        )
    return _operation_response(result, result.idempotency_key)


__all__ = [
    "BuildContextPayload",
    "CorrectPayload",
    "ExplainPayload",
    "KernelPayload",
    "ObservePayload",
    "ProposeBlockUpdatePayload",
    "RecallPayload",
    "ScopeInput",
    "SearchGraphPayload",
    "ValidationErrorDetail",
    "ValidationErrorResponse",
    "build_context",
    "correct",
    "explain",
    "get_memory_kernel",
    "get_operation_status",
    "observe",
    "propose_block_update",
    "recall",
    "router",
    "search_graph",
]

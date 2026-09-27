from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.db import get_db_session
from contexta.models.block import MemoryBlock
from contexta.models.consolidation import ConsolidatedObservation
from contexta.models.evidence import MemoryEvidence
from contexta.models.fact import MemoryFact
from contexta.models.proposal import MemoryProposal, ProposalValidationState
from contexta.repositories.block_repo import MemoryBlockRepository
from contexta.repositories.consolidation_repo import ConsolidatedObservationRepository
from contexta.repositories.evidence_repo import MemoryEvidenceRepository
from contexta.repositories.fact_repo import MemoryFactRepository
from contexta.repositories.identity_repo import AccountRepository, MemoryUserRepository
from contexta.repositories.proposal_repo import MemoryProposalRepository

router = APIRouter()
MAX_PAGE_SIZE = 100


class _ScopedResponse(BaseModel):
    organization_id: UUID
    user_id: UUID


class FactResponse(_ScopedResponse):
    id: UUID
    account_id: UUID | None = None
    memory_user_id: UUID | None = None
    agent_id: UUID | None = None
    project_id: UUID | None = None
    session_id: UUID | None = None
    episode_id: UUID | None = None
    subject: str
    predicate: str
    object: str
    value: Any = None
    value_type: str
    fact_key: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    known_at: datetime | None = None
    source_authority: str
    source_origin: str
    model_version: str | None = None
    source_id: str | None = None
    source_message_id: str | None = None
    lineage_id: str | None = None
    superseded_by_id: UUID | None = None
    confidence: float
    importance: float
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class EvidenceResponse(_ScopedResponse):
    id: UUID
    account_id: UUID | None = None
    memory_user_id: UUID | None = None
    agent_id: UUID | None = None
    project_id: UUID | None = None
    session_id: UUID | None = None
    episode_id: UUID | None = None
    source_turn_id: UUID | None = None
    observation_id: UUID | None = None
    fact_id: UUID | None = None
    evidence_key: str | None = None
    evidence_type: str
    content: str | None = None
    locator: str | None = None
    source_id: str | None = None
    source_message_id: str | None = None
    confidence: float
    source_authority: str
    source_origin: str
    model_version: str | None = None
    observed_at: datetime | None = None
    captured_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class MemoryProposalResponse(_ScopedResponse):
    id: UUID
    consolidated_observation_id: UUID | None = None
    proposal_type: str
    risk_tier: str
    validation_state: str
    admission_state: str
    status: str
    idempotency_key: str
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[UUID] = Field(default_factory=list)
    fact_keys: list[str] = Field(default_factory=list)
    supporting_ids: list[UUID] = Field(default_factory=list)
    source_observation_ids: list[UUID] = Field(default_factory=list)
    target_memory_ids: list[UUID] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float
    rationale: str = ""
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    canonical_memory_id: UUID | None = None
    validated_at: datetime | None = None
    rejected_at: datetime | None = None
    applied_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConsolidatedObservationResponse(_ScopedResponse):
    id: UUID
    observation_type: str
    content: str
    structured_data: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    risk_tier: str
    admission_state: str
    validation_state: str
    status: str
    confidence: float
    source_count: int
    evidence_ids: list[UUID] = Field(default_factory=list)
    supporting_ids: list[UUID] = Field(default_factory=list)
    source_observation_ids: list[UUID] = Field(default_factory=list)
    fact_keys: list[str] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    applied_memory_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MemoryBlockResponse(_ScopedResponse):
    id: UUID
    account_id: UUID | None = None
    memory_user_id: UUID | None = None
    agent_id: UUID | None = None
    project_id: UUID | None = None
    session_id: UUID | None = None
    block_key: str
    block_type: str
    name: str | None = None
    content: str | None = None
    structured_data: dict[str, Any] | None = None
    content_hash: str | None = None
    current_revision_id: UUID | None = None
    current_version: int
    status: str
    model_version: str | None = None
    source_authority: str
    source_origin: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


FactDetailResponse = FactResponse
EvidenceDetailResponse = EvidenceResponse
ProposalDetailResponse = MemoryProposalResponse
ConsolidatedObservationDetailResponse = ConsolidatedObservationResponse
MemoryBlockDetailResponse = MemoryBlockResponse
FactListResponse = list[FactResponse]
EvidenceListResponse = list[EvidenceResponse]
ProposalListResponse = list[MemoryProposalResponse]
ConsolidatedObservationListResponse = list[ConsolidatedObservationResponse]
MemoryBlockListResponse = list[MemoryBlockResponse]


def _state_uuid(request: Request, name: str) -> UUID | None:
    value = getattr(request.state, name, None)
    if value in (None, ""):
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return None


def _metadata(record: Any) -> dict[str, Any]:
    value = getattr(record, "metadata_", None)
    return dict(value) if isinstance(value, Mapping) else {}


def _values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, UUID)):
        return [value]
    return list(value)


async def _scope(
    request: Request,
    session: AsyncSession,
    *,
    user_id: UUID | None,
    organization_id: UUID | None,
) -> tuple[UUID, UUID]:
    tenant_id = _state_uuid(request, "organization_id")
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated organization context is required.",
        )
    if organization_id is not None and organization_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: organization_id mismatch.",
        )
    actor_id = _state_uuid(request, "actor_id")
    if actor_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user context is required.",
        )
    effective_user_id = user_id or actor_id
    if effective_user_id != actor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: user_id mismatch.",
        )
    memory_user_repository = MemoryUserRepository(session, tenant_id)
    if await memory_user_repository.get_by_id(effective_user_id) is not None:
        return tenant_id, effective_user_id
    account_repository = AccountRepository(session, tenant_id)
    if await account_repository.get_by_id(effective_user_id) is not None:
        return tenant_id, effective_user_id
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden: user is outside the authenticated organization.",
    )


async def _list_scoped(
    repository: Any,
    model: type[Any],
    user_id: UUID,
    *,
    offset: int,
    limit: int,
    order_by: Sequence[Any],
    filters: Sequence[Any] = (),
) -> list[Any]:
    statement = select(model).where(model.user_id == user_id, *filters)
    statement = repository._scope_select(statement).order_by(*order_by).offset(offset).limit(limit)
    result = await repository.session.execute(statement)
    return list(result.scalars().all())


def _belongs_to_scope(record: Any, tenant_id: UUID, user_id: UUID) -> bool:
    return (
        record is not None
        and getattr(record, "organization_id", None) == tenant_id
        and getattr(record, "user_id", None) == user_id
    )


def _fact_response(record: MemoryFact) -> FactResponse:
    return FactResponse(
        id=record.id,
        organization_id=record.organization_id,
        user_id=record.user_id,
        account_id=record.account_id,
        memory_user_id=record.memory_user_id,
        agent_id=record.agent_id,
        project_id=record.project_id,
        session_id=record.session_id,
        episode_id=record.episode_id,
        subject=record.subject,
        predicate=record.predicate,
        object=record.object,
        value=record.value,
        value_type=record.value_type,
        fact_key=record.fact_key,
        valid_from=record.valid_from,
        valid_to=record.valid_to,
        known_at=record.known_at,
        source_authority=record.source_authority,
        source_origin=record.source_origin,
        model_version=record.model_version,
        source_id=record.source_id,
        source_message_id=record.source_message_id,
        lineage_id=record.lineage_id,
        superseded_by_id=record.superseded_by_id,
        confidence=record.confidence,
        importance=record.importance,
        status=record.status,
        metadata=_metadata(record),
        created_at=record.created_at,
    )


def _evidence_response(record: MemoryEvidence) -> EvidenceResponse:
    return EvidenceResponse(
        id=record.id,
        organization_id=record.organization_id,
        user_id=record.user_id,
        account_id=record.account_id,
        memory_user_id=record.memory_user_id,
        agent_id=record.agent_id,
        project_id=record.project_id,
        session_id=record.session_id,
        episode_id=record.episode_id,
        source_turn_id=getattr(record, "source_turn_id_record", None),
        observation_id=record.observation_id,
        fact_id=record.fact_id,
        evidence_key=record.evidence_key,
        evidence_type=record.evidence_type,
        content=record.content,
        locator=record.locator,
        source_id=record.source_id,
        source_message_id=record.source_message_id,
        confidence=record.confidence,
        source_authority=record.source_authority,
        source_origin=record.source_origin,
        model_version=record.model_version,
        observed_at=record.observed_at,
        captured_at=record.captured_at,
        metadata=_metadata(record),
        created_at=record.created_at,
    )


def _proposal_response(record: MemoryProposal) -> MemoryProposalResponse:
    return MemoryProposalResponse(
        id=record.id,
        organization_id=record.organization_id,
        user_id=record.user_id,
        consolidated_observation_id=record.consolidated_observation_id,
        proposal_type=record.proposal_type,
        risk_tier=record.risk_tier,
        validation_state=record.validation_state,
        admission_state=record.admission_state,
        status=record.status,
        idempotency_key=record.idempotency_key,
        payload=dict(record.payload or {}),
        evidence_ids=_values(record.evidence_ids),
        fact_keys=_values(record.fact_keys),
        supporting_ids=_values(record.supporting_ids),
        source_observation_ids=_values(record.source_observation_ids),
        target_memory_ids=_values(record.target_memory_ids),
        evidence_refs=_values(record.evidence_refs),
        confidence=record.confidence,
        rationale=record.rationale,
        validation_errors=_values(record.validation_errors),
        metadata=_metadata(record),
        canonical_memory_id=record.canonical_memory_id,
        validated_at=record.validated_at,
        rejected_at=record.rejected_at,
        applied_at=record.applied_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _observation_response(record: ConsolidatedObservation) -> ConsolidatedObservationResponse:
    return ConsolidatedObservationResponse(
        id=record.id,
        organization_id=record.organization_id,
        user_id=record.user_id,
        observation_type=record.observation_type,
        content=record.content,
        structured_data=dict(record.structured_data or {}),
        idempotency_key=record.idempotency_key,
        risk_tier=record.risk_tier,
        admission_state=record.admission_state,
        validation_state=record.validation_state,
        status=record.status,
        confidence=record.confidence,
        source_count=record.source_count,
        evidence_ids=_values(record.evidence_ids),
        supporting_ids=_values(record.supporting_ids),
        source_observation_ids=_values(record.source_observation_ids),
        fact_keys=_values(record.fact_keys),
        evidence_refs=_values(record.evidence_refs),
        metadata=_metadata(record),
        applied_memory_id=record.applied_memory_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _block_response(record: MemoryBlock) -> MemoryBlockResponse:
    return MemoryBlockResponse(
        id=record.id,
        organization_id=record.organization_id,
        user_id=record.user_id,
        account_id=record.account_id,
        memory_user_id=record.memory_user_id,
        agent_id=record.agent_id,
        project_id=record.project_id,
        session_id=record.session_id,
        block_key=record.block_key,
        block_type=record.block_type,
        name=record.name,
        content=record.content,
        structured_data=record.structured_data,
        content_hash=record.content_hash,
        current_revision_id=record.current_revision_id,
        current_version=record.current_version,
        status=record.status,
        model_version=record.model_version,
        source_authority=record.source_authority,
        source_origin=record.source_origin,
        valid_from=record.valid_from,
        valid_to=record.valid_to,
        metadata=_metadata(record),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/facts", response_model=FactListResponse)
async def list_facts(
    request: Request,
    user_id: UUID | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    fact_status: str | None = Query(default=None, alias="status", min_length=1, max_length=32),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_db_session),
) -> FactListResponse:
    tenant_id, effective_user_id = await _scope(
        request,
        session,
        user_id=user_id,
        organization_id=organization_id,
    )
    repository = MemoryFactRepository(session, tenant_id)
    filters = (MemoryFact.status == fact_status,) if fact_status else ()
    records = await _list_scoped(
        repository,
        MemoryFact,
        effective_user_id,
        offset=offset,
        limit=limit,
        order_by=(MemoryFact.created_at.desc(), MemoryFact.id.desc()),
        filters=filters,
    )
    return [_fact_response(record) for record in records]


@router.get("/facts/{fact_id}", response_model=FactDetailResponse)
async def get_fact(
    fact_id: UUID,
    request: Request,
    user_id: UUID | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> FactDetailResponse:
    tenant_id, effective_user_id = await _scope(
        request,
        session,
        user_id=user_id,
        organization_id=organization_id,
    )
    repository = MemoryFactRepository(session, tenant_id)
    record = await repository.get_by_id(fact_id)
    if not _belongs_to_scope(record, tenant_id, effective_user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found.")
    return _fact_response(record)


@router.get("/evidence", response_model=EvidenceListResponse)
async def list_evidence(
    request: Request,
    user_id: UUID | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    fact_id: UUID | None = Query(default=None),
    episode_id: UUID | None = Query(default=None),
    source_turn_id: UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_db_session),
) -> EvidenceListResponse:
    tenant_id, effective_user_id = await _scope(
        request,
        session,
        user_id=user_id,
        organization_id=organization_id,
    )
    repository = MemoryEvidenceRepository(session, tenant_id)
    filters: list[Any] = []
    if fact_id is not None:
        filters.append(MemoryEvidence.fact_id == fact_id)
    if episode_id is not None:
        filters.append(MemoryEvidence.episode_id == episode_id)
    if source_turn_id is not None:
        filters.append(MemoryEvidence.source_turn_id_record == source_turn_id)
    records = await _list_scoped(
        repository,
        MemoryEvidence,
        effective_user_id,
        offset=offset,
        limit=limit,
        order_by=(MemoryEvidence.created_at.desc(), MemoryEvidence.id.desc()),
        filters=filters,
    )
    return [_evidence_response(record) for record in records]


@router.get("/evidence/{evidence_id}", response_model=EvidenceDetailResponse)
async def get_evidence(
    evidence_id: UUID,
    request: Request,
    user_id: UUID | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> EvidenceDetailResponse:
    tenant_id, effective_user_id = await _scope(
        request,
        session,
        user_id=user_id,
        organization_id=organization_id,
    )
    repository = MemoryEvidenceRepository(session, tenant_id)
    record = await repository.get_by_id(evidence_id)
    if not _belongs_to_scope(record, tenant_id, effective_user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found.")
    return _evidence_response(record)


@router.get("/proposals", response_model=ProposalListResponse)
async def list_proposals(
    request: Request,
    user_id: UUID | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    validation_state: str | None = Query(default=None, min_length=1, max_length=32),
    proposal_type: str | None = Query(default=None, min_length=1, max_length=32),
    risk_tier: str | None = Query(default=None, min_length=1, max_length=16),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_db_session),
) -> ProposalListResponse:
    tenant_id, effective_user_id = await _scope(
        request,
        session,
        user_id=user_id,
        organization_id=organization_id,
    )
    repository = MemoryProposalRepository(session, tenant_id)
    filters: list[Any] = []
    if validation_state is not None:
        filters.append(MemoryProposal.validation_state == validation_state)
    if proposal_type is not None:
        filters.append(MemoryProposal.proposal_type == proposal_type)
    if risk_tier is not None:
        filters.append(MemoryProposal.risk_tier == risk_tier)
    records = await _list_scoped(
        repository,
        MemoryProposal,
        effective_user_id,
        offset=offset,
        limit=limit,
        order_by=(MemoryProposal.created_at.desc(), MemoryProposal.id.desc()),
        filters=filters,
    )
    return [_proposal_response(record) for record in records]


@router.get("/proposals/review-queue", response_model=ProposalListResponse)
async def list_proposal_review_queue(
    request: Request,
    user_id: UUID | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_db_session),
) -> ProposalListResponse:
    tenant_id, effective_user_id = await _scope(
        request,
        session,
        user_id=user_id,
        organization_id=organization_id,
    )
    repository = MemoryProposalRepository(session, tenant_id)
    records = await _list_scoped(
        repository,
        MemoryProposal,
        effective_user_id,
        offset=offset,
        limit=limit,
        order_by=(MemoryProposal.risk_tier.desc(), MemoryProposal.created_at.asc(), MemoryProposal.id.asc()),
        filters=(
            MemoryProposal.validation_state.in_(
                (
                    ProposalValidationState.PENDING.value,
                    ProposalValidationState.NEEDS_REVIEW.value,
                )
            ),
        ),
    )
    return [_proposal_response(record) for record in records]


@router.get("/proposals/{proposal_id}", response_model=ProposalDetailResponse)
async def get_proposal(
    proposal_id: UUID,
    request: Request,
    user_id: UUID | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ProposalDetailResponse:
    tenant_id, effective_user_id = await _scope(
        request,
        session,
        user_id=user_id,
        organization_id=organization_id,
    )
    repository = MemoryProposalRepository(session, tenant_id)
    record = await repository.get_by_id(proposal_id)
    if not _belongs_to_scope(record, tenant_id, effective_user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found.")
    return _proposal_response(record)


@router.get("/consolidated-observations", response_model=ConsolidatedObservationListResponse)
async def list_consolidated_observations(
    request: Request,
    user_id: UUID | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    validation_state: str | None = Query(default=None, min_length=1, max_length=32),
    status_filter: str | None = Query(default=None, alias="status", min_length=1, max_length=32),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_db_session),
) -> ConsolidatedObservationListResponse:
    tenant_id, effective_user_id = await _scope(
        request,
        session,
        user_id=user_id,
        organization_id=organization_id,
    )
    repository = ConsolidatedObservationRepository(session, tenant_id)
    filters: list[Any] = []
    if validation_state is not None:
        filters.append(ConsolidatedObservation.validation_state == validation_state)
    if status_filter is not None:
        filters.append(ConsolidatedObservation.status == status_filter)
    records = await _list_scoped(
        repository,
        ConsolidatedObservation,
        effective_user_id,
        offset=offset,
        limit=limit,
        order_by=(ConsolidatedObservation.created_at.desc(), ConsolidatedObservation.id.desc()),
        filters=filters,
    )
    return [_observation_response(record) for record in records]


@router.get("/consolidated-observations/{observation_id}", response_model=ConsolidatedObservationDetailResponse)
async def get_consolidated_observation(
    observation_id: UUID,
    request: Request,
    user_id: UUID | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ConsolidatedObservationDetailResponse:
    tenant_id, effective_user_id = await _scope(
        request,
        session,
        user_id=user_id,
        organization_id=organization_id,
    )
    repository = ConsolidatedObservationRepository(session, tenant_id)
    record = await repository.get_by_id(observation_id)
    if not _belongs_to_scope(record, tenant_id, effective_user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Consolidated observation not found.",
        )
    return _observation_response(record)


@router.get("/blocks", response_model=MemoryBlockListResponse)
async def list_memory_blocks(
    request: Request,
    user_id: UUID | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    block_type: str | None = Query(default=None, min_length=1, max_length=50),
    status_filter: str | None = Query(default=None, alias="status", min_length=1, max_length=32),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_db_session),
) -> MemoryBlockListResponse:
    tenant_id, effective_user_id = await _scope(
        request,
        session,
        user_id=user_id,
        organization_id=organization_id,
    )
    repository = MemoryBlockRepository(session, tenant_id)
    filters: list[Any] = []
    if block_type is not None:
        filters.append(MemoryBlock.block_type == block_type)
    if status_filter is not None:
        filters.append(MemoryBlock.status == status_filter)
    records = await _list_scoped(
        repository,
        MemoryBlock,
        effective_user_id,
        offset=offset,
        limit=limit,
        order_by=(MemoryBlock.updated_at.desc(), MemoryBlock.id.desc()),
        filters=filters,
    )
    return [_block_response(record) for record in records]


@router.get("/blocks/{block_id}", response_model=MemoryBlockDetailResponse)
async def get_memory_block(
    block_id: UUID,
    request: Request,
    user_id: UUID | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> MemoryBlockDetailResponse:
    tenant_id, effective_user_id = await _scope(
        request,
        session,
        user_id=user_id,
        organization_id=organization_id,
    )
    repository = MemoryBlockRepository(session, tenant_id)
    record = await repository.get_by_id(block_id)
    if not _belongs_to_scope(record, tenant_id, effective_user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory block not found.")
    return _block_response(record)


__all__ = [
    "ConsolidatedObservationDetailResponse",
    "ConsolidatedObservationListResponse",
    "ConsolidatedObservationResponse",
    "EvidenceDetailResponse",
    "EvidenceListResponse",
    "EvidenceResponse",
    "FactDetailResponse",
    "FactListResponse",
    "FactResponse",
    "MemoryBlockDetailResponse",
    "MemoryBlockListResponse",
    "MemoryBlockResponse",
    "MemoryProposalResponse",
    "ProposalDetailResponse",
    "ProposalListResponse",
    "get_consolidated_observation",
    "get_evidence",
    "get_fact",
    "get_memory_block",
    "get_proposal",
    "list_consolidated_observations",
    "list_evidence",
    "list_facts",
    "list_memory_blocks",
    "list_proposal_review_queue",
    "list_proposals",
    "router",
]

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

CANONICAL_WRITE_AUTHORITY: Literal["contexta"] = "contexta"
CanonicalWriteAuthority = Literal["contexta"]


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )


class WriteAuthority(str, Enum):
    CONTEXTA = CANONICAL_WRITE_AUTHORITY


class OperationKind(str, Enum):
    OBSERVE = "observe"
    RECALL = "recall"
    BUILD_CONTEXT = "build_context"
    EXPLAIN = "explain"
    CORRECT = "correct"
    PROPOSE_BLOCK_UPDATE = "propose_block_update"
    SEARCH_GRAPH = "search_graph"
    GET_OPERATION = "get_operation"
    OTHER = "other"


class OperationStatus(str, Enum):
    ACCEPTED = "accepted"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    PROPOSED = "proposed"
    CANCELLED = "cancelled"


class EvidenceKind(str, Enum):
    OBSERVATION = "observation"
    MESSAGE = "message"
    MEMORY = "memory"
    GRAPH = "graph"
    EXTERNAL = "external"


class GraphDirection(str, Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"
    BOTH = "both"


class BlockUpdateOperation(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    MERGE = "merge"


class Scope(ContractModel):
    tenant_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("tenant_id", "organization_id", "org_id"),
    )
    user_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("user_id", "actor_id"),
    )
    account_id: str | None = Field(default=None, min_length=1)
    memory_user_id: str | None = Field(default=None, min_length=1)
    agent_id: str | None = Field(default=None, min_length=1)
    project_id: str | None = Field(default=None, min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "tenant_id",
        "user_id",
        "account_id",
        "memory_user_id",
        "agent_id",
        "project_id",
        "session_id",
        mode="before",
    )
    @classmethod
    def normalize_identifier(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("scope identifiers must not be empty")
        return normalized

    @property
    def organization_id(self) -> str:
        return self.tenant_id

    @property
    def org_id(self) -> str:
        return self.tenant_id

    @property
    def actor_id(self) -> str:
        return self.user_id

    @property
    def subject_id(self) -> str:
        return self.memory_user_id or self.user_id


RuntimeScope = Scope
TenantScope = Scope
RequestScope = Scope


class ScopedRequest(ContractModel):
    scope: Scope
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)
    request_id: str | None = Field(default=None, min_length=1, max_length=255)
    write_authority: CanonicalWriteAuthority = CANONICAL_WRITE_AUTHORITY
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("idempotency_key", "request_id", mode="before")
    @classmethod
    def normalize_key(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("request identifiers must not be empty")
        return normalized

    @property
    def tenant_id(self) -> str:
        return self.scope.tenant_id

    @property
    def user_id(self) -> str:
        return self.scope.user_id

    @property
    def account_id(self) -> str:
        return self.scope.account_id or self.scope.user_id

    @property
    def memory_user_id(self) -> str:
        return self.scope.memory_user_id or self.scope.user_id

    @property
    def agent_id(self) -> str | None:
        return self.scope.agent_id

    @property
    def project_id(self) -> str | None:
        return self.scope.project_id

    @property
    def session_id(self) -> str | None:
        return self.scope.session_id


class WriteRequest(ScopedRequest):
    idempotency_key: str = Field(min_length=1, max_length=255)


class EvidenceRef(ContractModel):
    id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("id", "evidence_id", "reference_id"),
    )
    kind: EvidenceKind = EvidenceKind.MEMORY
    source_id: str | None = Field(default=None, min_length=1)
    message_id: str | None = Field(default=None, min_length=1)
    observation_id: str | None = Field(default=None, min_length=1)
    memory_id: str | None = Field(default=None, min_length=1)
    operation_id: str | None = Field(default=None, min_length=1)
    uri: str | None = Field(default=None, min_length=1)
    excerpt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "id",
        "source_id",
        "message_id",
        "observation_id",
        "memory_id",
        "operation_id",
        "uri",
        mode="before",
    )
    @classmethod
    def normalize_reference_value(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("evidence references must not be empty")
        return normalized

    @property
    def evidence_id(self) -> str:
        return self.id

    @property
    def reference_id(self) -> str:
        return self.id


EvidenceReference = EvidenceRef


class OperationError(ContractModel):
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1)
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class OperationResult(ContractModel):
    operation_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    kind: OperationKind = OperationKind.OTHER
    status: OperationStatus = OperationStatus.COMPLETED
    scope: Scope
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)
    write_authority: CanonicalWriteAuthority = CANONICAL_WRITE_AUTHORITY
    result: Any | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    error: OperationError | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status == OperationStatus.COMPLETED


OperationReceipt = OperationResult


class ObservationMessage(ContractModel):
    role: str = "user"
    content: str = Field(min_length=1)
    message_id: str | None = Field(default=None, min_length=1)
    occurred_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("role", "message_id", mode="before")
    @classmethod
    def normalize_message_field(cls, value: Any) -> Any:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class ObservationEvent(ContractModel):
    content: str = Field(min_length=1)
    event_id: str | None = Field(default=None, min_length=1)
    source_id: str | None = Field(default=None, min_length=1)
    occurred_at: datetime | None = None
    observed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id", "source_id", mode="before")
    @classmethod
    def normalize_event_field(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class ObserveRequest(WriteRequest):
    content: str | None = Field(default=None, min_length=1)
    messages: list[ObservationMessage] = Field(default_factory=list)
    events: list[ObservationEvent] = Field(default_factory=list)
    occurred_at: datetime | None = None
    observed_at: datetime | None = None
    source_id: str | None = Field(default=None, min_length=1)
    timezone: str | None = Field(default=None, min_length=1)
    policy: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_observation_payload(self) -> ObserveRequest:
        if self.content is None and not self.messages and not self.events:
            raise ValueError("observe requires content, messages, or events")
        return self


class ObserveResult(OperationResult):
    kind: OperationKind = OperationKind.OBSERVE
    status: OperationStatus = OperationStatus.ACCEPTED
    observation_id: str | None = None
    accepted_event_ids: list[str] = Field(default_factory=list)
    memory_ids: list[str] = Field(default_factory=list)


class RecallRequest(ScopedRequest):
    query: str = Field(
        min_length=1,
        validation_alias=AliasChoices("query", "query_text"),
    )
    limit: int = Field(default=20, ge=1, le=100)
    graph_depth: int = Field(default=2, ge=0, le=5)
    memory_types: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    include_cold: bool = True
    include_archived: bool = False
    include_evidence: bool = True
    as_of: datetime | None = None
    temporal_mode: str = "auto"

    @property
    def query_text(self) -> str:
        return self.query


class MemoryHit(ContractModel):
    memory_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("memory_id", "id"),
    )
    title: str | None = None
    content: str
    memory_type: str
    score: float = 0.0
    scores: dict[str, float] = Field(default_factory=dict)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.memory_id


class RecallResult(OperationResult):
    kind: OperationKind = OperationKind.RECALL
    query: str = ""
    results: list[MemoryHit] = Field(default_factory=list)
    total: int = 0

    @property
    def items(self) -> list[MemoryHit]:
        return self.results

    @property
    def memories(self) -> list[MemoryHit]:
        return self.results


class ExplainRequest(ScopedRequest):
    memory_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("memory_id", "id"),
    )
    question: str | None = Field(default=None, min_length=1)
    include_evidence: bool = True

    @property
    def id(self) -> str:
        return self.memory_id


class ExplanationResult(OperationResult):
    kind: OperationKind = OperationKind.EXPLAIN
    memory_id: str
    summary: str
    rationale: list[str] = Field(default_factory=list)
    supporting_evidence: list[EvidenceRef] = Field(default_factory=list)
    counter_evidence: list[EvidenceRef] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)

    # ContractModel is frozen, so the copy of supporting_evidence has to happen
    # before the instance exists. An "after" validator assigning to self.evidence
    # raised frozen_instance, which made every /v1/kernel/explain call a 500.
    @model_validator(mode="before")
    @classmethod
    def synchronize_evidence(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and not data.get("evidence"):
            return {**data, "evidence": list(data.get("supporting_evidence") or [])}
        return data

    @property
    def all_evidence(self) -> list[EvidenceRef]:
        return [*self.evidence, *self.counter_evidence]


class CorrectRequest(WriteRequest):
    memory_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("memory_id", "id"),
    )
    corrected_content: str = Field(
        min_length=1,
        validation_alias=AliasChoices("corrected_content", "content", "correction"),
    )
    reason: str | None = Field(default=None, min_length=1)
    evidence: list[EvidenceRef] = Field(default_factory=list)

    @property
    def id(self) -> str:
        return self.memory_id


class CorrectionResult(OperationResult):
    kind: OperationKind = OperationKind.CORRECT
    memory_id: str
    memory_version_id: str | None = None
    superseded_memory_id: str | None = None
    status_detail: str | None = None


class ProposeBlockUpdateRequest(WriteRequest):
    block_id: str | None = Field(default=None, min_length=1)
    operation: BlockUpdateOperation = BlockUpdateOperation.UPDATE
    content: str = Field(min_length=1)
    expected_version: int | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, min_length=1)
    evidence: list[EvidenceRef] = Field(default_factory=list)


BlockUpdateRequest = ProposeBlockUpdateRequest


class BlockUpdateProposal(OperationResult):
    kind: OperationKind = OperationKind.PROPOSE_BLOCK_UPDATE
    status: OperationStatus = OperationStatus.PROPOSED
    proposal_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    block_id: str | None = None
    operation: BlockUpdateOperation
    content: str
    expected_version: int | None = None
    applied: bool = False
    requires_review: bool = True


class SearchGraphRequest(ScopedRequest):
    query: str | None = Field(default=None, min_length=1)
    root_entity_id: str | None = Field(default=None, min_length=1)
    entity_ids: list[str] = Field(default_factory=list)
    relationship_types: list[str] = Field(default_factory=list)
    direction: GraphDirection = GraphDirection.BOTH
    max_hops: int = Field(default=2, ge=1, le=5)
    limit: int = Field(default=50, ge=1, le=500)
    include_evidence: bool = True

    @model_validator(mode="after")
    def require_graph_target(self) -> SearchGraphRequest:
        if not self.query and not self.root_entity_id and not self.entity_ids:
            raise ValueError("graph search requires query, root_entity_id, or entity_ids")
        return self


class GraphNode(ContractModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    entity_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(ContractModel):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    relationship_type: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LinkedMemory(ContractModel):
    memory_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("memory_id", "id"),
    )
    title: str | None = None
    content: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)

    @property
    def id(self) -> str:
        return self.memory_id


class GraphSearchResult(OperationResult):
    kind: OperationKind = OperationKind.SEARCH_GRAPH
    query: str | None = None
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    linked_memories: list[LinkedMemory] = Field(default_factory=list)


class GetOperationRequest(ScopedRequest):
    operation_id: str = Field(min_length=1)

    @property
    def id(self) -> str:
        return self.operation_id


def dump_model(model: BaseModel, *, by_alias: bool = True) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=by_alias)


def load_model(model_type: type[ContractModel], payload: Mapping[str, Any] | str) -> ContractModel:
    if isinstance(payload, str):
        return model_type.model_validate_json(payload)
    return model_type.model_validate(dict(payload))


def json_dumps(value: Any, *, indent: int | None = None) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":") if indent is None else None, indent=indent)

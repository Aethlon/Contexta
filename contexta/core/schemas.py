"""Pydantic models for core data structures in the contexta memory engine."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from contexta.core.types import MemoryType, SourceType


def _normalize_scope_uuid(value: Any) -> Any:
    if value is None or isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    return value


class ObservationPayload(BaseModel):
    """Payload submitted to the Observation Engine for memory extraction."""

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    @field_validator(
        "user_id",
        "memory_user_id",
        "agent_id",
        "project_id",
        "organization_id",
        "session_id",
        mode="before",
    )
    @classmethod
    def normalize_scope_uuid(cls, value: Any) -> Any:
        return _normalize_scope_uuid(value)

    user_id: UUID
    memory_user_id: UUID | None = None
    agent_id: UUID | None = None
    project_id: UUID | None = None
    organization_id: UUID
    session_id: UUID
    messages: list[dict] = Field(
        ..., description="User, assistant, and tool messages from the conversation."
    )
    occurred_at: datetime | None = Field(
        default=None, description="Timestamp for when the observation occurred."
    )
    observed_at: datetime | None = Field(
        default=None, description="Timestamp for when the observation was observed."
    )
    event_at: datetime | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    temporal_precision: str | None = None
    temporal_basis: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    source_span: dict[str, Any] | None = None
    source_id: Any = Field(
        default=None, description="Optional source identifier for the observation."
    )
    message_id: Any = Field(
        default=None, description="Optional message identifier for the observation."
    )
    source_message_id: Any = None
    timezone: str | None = Field(
        default=None, description="Optional IANA timezone for temporal grounding."
    )
    original_text: str | None = None
    normalized_text: str | None = None
    metadata: dict | None = None
    policy: str | None = Field(
        default=None, description="Named policy to apply during extraction."
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_field_aliases(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        result = dict(value)
        if "temporal_precision" not in result and "precision" in result:
            result["temporal_precision"] = result["precision"]
        if "temporal_basis" not in result and "basis" in result:
            result["temporal_basis"] = result["basis"]
        if "source_span" not in result and isinstance(result.get("span"), Mapping):
            result["source_span"] = dict(result["span"])
        if "timezone" not in result and "event_timezone" in result:
            result["timezone"] = result["event_timezone"]
        return result

    @property
    def precision(self) -> str | None:
        return self.temporal_precision

    @property
    def basis(self) -> str | None:
        return self.temporal_basis

    @property
    def span(self) -> dict[str, Any] | None:
        return self.source_span


class ExtractedMemory(BaseModel):
    """A structured memory produced by the Extraction Worker."""

    model_config = ConfigDict(extra="allow")

    memory_type: MemoryType
    source_type: SourceType
    title: str = Field(..., min_length=1)
    content: str
    structured_data: dict | None = None
    tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(
        default_factory=list,
        description="Entity references for resolution.",
    )
    has_emphasis: bool = False
    impacts_decisions: bool = False
    event_at: datetime | None = Field(
        default=None, description="Absolute time of the event described by the memory."
    )
    event_start: datetime | None = Field(
        default=None, description="Inclusive start of the event interval."
    )
    event_end: datetime | None = Field(
        default=None, description="Inclusive end of the event interval."
    )
    observed_at: datetime | None = Field(
        default=None, description="Time the source observation was observed."
    )
    timezone: str | None = Field(
        default=None, description="Timezone used to resolve temporal expressions."
    )
    event_timezone: str | None = None
    temporal_precision: str | None = None
    temporal_basis: str | None = None
    source_id: str | None = None
    message_id: str | None = None
    source_message_id: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    source_span: dict[str, Any] | None = None
    original_text: str | None = None
    normalized_text: str | None = None
    original_title: str | None = None
    normalized_title: str | None = None
    temporal: dict[str, Any] | None = None
    tables: list[dict[str, Any]] = Field(default_factory=list)
    table: dict[str, Any] | None = None
    table_rows: list[dict[str, Any]] = Field(default_factory=list)
    assignment_candidates: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_field_aliases(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        result = dict(value)
        if "temporal_precision" not in result and "precision" in result:
            result["temporal_precision"] = result["precision"]
        if "temporal_basis" not in result and "basis" in result:
            result["temporal_basis"] = result["basis"]
        if "source_span" not in result and isinstance(result.get("span"), Mapping):
            result["source_span"] = dict(result["span"])
        if "timezone" not in result and "event_timezone" in result:
            result["timezone"] = result["event_timezone"]
        if "message_id" not in result and "source_message_id" in result:
            result["message_id"] = result["source_message_id"]
        return result

    @model_validator(mode="after")
    def _synchronize_provenance(self) -> ExtractedMemory:
        if self.event_start is None and self.event_at is not None:
            self.event_start = self.event_at
        if self.event_at is None and self.event_start is not None:
            self.event_at = self.event_start
        if self.event_timezone is None and self.timezone is not None:
            self.event_timezone = self.timezone
        if self.timezone is None and self.event_timezone is not None:
            self.timezone = self.event_timezone
        if self.source_message_id is None and self.message_id is not None:
            self.source_message_id = self.message_id
        if self.message_id is None and self.source_message_id is not None:
            self.message_id = self.source_message_id
        if self.source_span is None and self.source_start is not None and self.source_end is not None:
            self.source_span = {"start": self.source_start, "end": self.source_end}
        if self.source_start is None and isinstance(self.source_span, dict):
            self.source_start = self.source_span.get("start")
        if self.source_end is None and isinstance(self.source_span, dict):
            self.source_end = self.source_span.get("end")
        if self.original_text is None:
            self.original_text = self.content
        if self.normalized_text is None:
            self.normalized_text = self.content
        return self

    @property
    def precision(self) -> str | None:
        return self.temporal_precision

    @property
    def basis(self) -> str | None:
        return self.temporal_basis

    @property
    def span(self) -> dict[str, Any] | None:
        return self.source_span


class ImportanceSignals(BaseModel):
    """Contextual signals used by the Importance Framework to compute modifiers."""

    mention_count: int = Field(default=0, ge=0)
    last_referenced: datetime | None = None
    has_emphasis: bool = False
    impacts_decisions: bool = False
    utility_ratio: float | None = Field(default=None, ge=0.0, le=1.0)


class TokenAllocation(BaseModel):
    """Token budget allocation across memory categories."""

    total_budget: int = Field(..., gt=0)
    allocations: dict[str, int] = Field(
        default_factory=dict,
        description="Category to allocated token count mapping.",
    )
    actual_usage: dict[str, int] = Field(
        default_factory=dict,
        description="Category to actual tokens used mapping.",
    )


class RetrievalQuery(BaseModel):
    """Query parameters for the hybrid Retrieval Engine."""

    model_config = ConfigDict(validate_assignment=True)

    @field_validator(
        "user_id",
        "memory_user_id",
        "agent_id",
        "project_id",
        "organization_id",
        "session_id",
        mode="before",
    )
    @classmethod
    def normalize_scope_uuid(cls, value: Any) -> Any:
        return _normalize_scope_uuid(value)

    user_id: UUID
    memory_user_id: UUID | None = None
    agent_id: UUID | None = None
    project_id: UUID | None = None
    session_id: UUID | None = None
    organization_id: UUID
    query_text: str = Field(..., min_length=1)
    memory_types: list[MemoryType] | None = Field(
        default=None,
        description="Filter results to specific memory types.",
    )
    tags: list[str] | None = None
    limit: int = Field(default=20, gt=0, le=100)
    graph_depth: int = Field(
        default=2, ge=0, le=5, description="Max hops for graph expansion."
    )
    include_cold: bool = Field(
        default=True, description="Whether to include cold-state memories (with penalty)."
    )
    include_archived: bool = Field(
        default=False, description="Whether to include archived memories."
    )
    as_of: datetime | None = Field(
        default=None, description="Reference time for temporal retrieval."
    )
    temporal_mode: str = Field(
        default="auto", description="Temporal mode: auto, current, as_of, or range."
    )


class ContextConfig(BaseModel):
    """Configuration parameters for context assembly."""

    num_recent_messages: int = Field(default=10, gt=0)
    num_relevant_memories: int = Field(default=20, gt=0)
    graph_depth: int = Field(default=2, ge=0, le=5)
    include_user_model: bool = True
    token_budget: int | None = Field(
        default=None, gt=0, description="Total token budget for context assembly."
    )
    custom_weights: dict[str, float] | None = Field(
        default=None,
        description="Custom category weight overrides for token allocation.",
    )


class ContextRequest(BaseModel):
    """Request to the Context Builder for assembled agent context."""

    model_config = ConfigDict(validate_assignment=True)

    @field_validator(
        "user_id",
        "memory_user_id",
        "agent_id",
        "project_id",
        "organization_id",
        "session_id",
        mode="before",
    )
    @classmethod
    def normalize_scope_uuid(cls, value: Any) -> Any:
        return _normalize_scope_uuid(value)

    user_id: UUID
    memory_user_id: UUID | None = None
    agent_id: UUID | None = None
    project_id: UUID | None = None
    organization_id: UUID
    session_id: UUID
    config: ContextConfig = Field(default_factory=ContextConfig)

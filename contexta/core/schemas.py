"""Pydantic models for core data structures in the contexta memory engine."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from contexta.core.types import MemoryType, SourceType


class ObservationPayload(BaseModel):
    """Payload submitted to the Observation Engine for memory extraction."""

    user_id: UUID
    organization_id: UUID
    session_id: UUID
    messages: list[dict] = Field(
        ..., description="User, assistant, and tool messages from the conversation."
    )
    metadata: dict | None = None
    policy: str | None = Field(
        default=None, description="Named policy to apply during extraction."
    )


class ExtractedMemory(BaseModel):
    """A structured memory produced by the Extraction Worker."""

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

    user_id: UUID
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

    user_id: UUID
    organization_id: UUID
    session_id: UUID
    config: ContextConfig = Field(default_factory=ContextConfig)

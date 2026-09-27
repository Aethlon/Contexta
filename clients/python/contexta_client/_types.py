from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class contextaError(Exception):
    pass


class AuthenticationError(contextaError):
    pass


class AuthorizationError(contextaError):
    pass


class ValidationError(contextaError):
    def __init__(self, message: str, fields: list[dict[str, str]] | None = None) -> None:
        super().__init__(message)
        self.fields = fields or []


class QuotaExceeded(contextaError):
    pass


class RateLimited(contextaError):
    def __init__(self, message: str, retry_after: int = 0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ServerError(contextaError):
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


class NotFoundError(contextaError):
    pass


class ConflictError(contextaError):
    pass


class ObserveResponse(BaseModel):
    job_id: str
    observation_id: str | None = None
    status: str = "accepted"


class ValidationErrorDetail(BaseModel):
    field: str
    message: str


class BatchObserveResponse(BaseModel):
    jobs: list[ObserveResponse] = []
    errors: list[ValidationErrorDetail] = []
    status: str = "accepted"


class ScoreBreakdown(BaseModel):
    semantic: float = 0.0
    graph: float = 0.0
    importance: float = 0.0
    recency: float = 0.0
    keyword: float = 0.0


class Memory(BaseModel):
    """Mirrors the server's ``MemoryDetailResponse`` payload."""

    id: str
    user_id: str = ""
    organization_id: str = ""
    memory_type: str = ""
    title: str = ""
    content: str = ""
    structured_data: dict[str, Any] | None = None
    source_type: str = ""
    confidence: float = 0.0
    importance: float = 0.0
    utility_score: float = 0.0
    tags: list[str] | None = None
    session_id: str | None = None
    memory_state: str = ""
    is_pinned: bool = False
    is_archived: bool = False
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_accessed_at: datetime | None = None


class ScoredMemory(BaseModel):
    """A single entry of ``POST /v1/retrieve`` / ``/v1/retrieve/batch``."""

    memory: Memory | None = None
    score: float = 0.0
    semantic_score: float = 0.0
    graph_score: float = 0.0
    importance_score: float = 0.0
    recency_score: float = 0.0
    keyword_score: float = 0.0


class MemoryListEntry(BaseModel):
    """One element of ``GET /v1/memories``."""

    id: str
    title: str = ""
    memory_type: str = ""
    memory_state: str = ""
    importance: float = 0.0
    confidence: float = 0.0
    tags: list[str] | None = None
    is_pinned: bool = False
    is_archived: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MemoryFlag(BaseModel):
    """Response of the ``pin`` / ``unpin`` / ``archive`` / ``restore`` routes."""

    memory_id: str
    is_pinned: bool | None = None
    is_archived: bool | None = None


class DeleteResult(BaseModel):
    memory_id: str
    deleted: bool = True


class TokenUsage(BaseModel):
    total: int = 0
    by_section: dict[str, int] = {}


class ContextSection(BaseModel):
    title: str = ""
    content: str = ""
    tokens: int = 0


class UserProfile(BaseModel):
    user_id: str = ""
    name: str = ""
    preferences: list[str] = []
    traits: dict[str, Any] = {}


class Project(BaseModel):
    project_id: str = ""
    name: str = ""
    description: str = ""
    status: str = ""


class Goal(BaseModel):
    goal_id: str = ""
    description: str = ""
    status: str = ""
    progress: float = 0.0


class Preference(BaseModel):
    preference_id: str = ""
    category: str = ""
    value: str = ""
    confidence: float = 0.0


class Event(BaseModel):
    event_id: str = ""
    event_type: str = ""
    description: str = ""
    timestamp: datetime | None = None
    metadata: dict[str, Any] = {}


class Context(BaseModel):
    """Assembled context returned by ``GET /v1/memories/context``.

    Every section is emitted by the server's context builder as a free-form JSON
    object, so the sections stay as dictionaries rather than being coerced into
    narrow models that would drop fields.
    """

    user_profile: dict[str, Any] | None = None
    rules: list[dict[str, Any]] = []
    active_projects: list[dict[str, Any]] = []
    preferences: list[dict[str, Any]] = []
    goals: list[dict[str, Any]] = []
    recent_events: list[dict[str, Any]] = []
    relevant_memories: list[dict[str, Any]] = []
    token_usage: TokenUsage | None = None
    cache_hit: bool = False
    request_id: str = ""


class Explanation(BaseModel):
    """Scoring and supersession breakdown from ``GET /v1/memories/{id}/explain``."""

    memory_id: str
    source: dict[str, Any] = {}
    classification: dict[str, Any] = {}
    scoring: dict[str, Any] = {}
    supersession_history: list[dict[str, Any]] = []


class TimelineEvent(BaseModel):
    """One element of ``GET /v1/memories/timeline/{user_id}``."""

    id: str
    event_type: str = ""
    timestamp: datetime | None = None
    memory: dict[str, Any] = {}


class TimelineResponse(BaseModel):
    user_id: str = ""
    events: list[TimelineEvent] = []


class FieldDef(BaseModel):
    name: str
    type: str
    required: bool = False
    values: list[str] | None = None
    description: str = ""


class Schema(BaseModel):
    schema_id: str = ""
    name: str
    field_definitions: list[FieldDef] = []
    created_at: datetime | None = None


class Policy(BaseModel):
    policy_id: str = ""
    name: str
    store_rules: list[dict[str, Any]] = []
    ignore_rules: list[dict[str, Any]] = []
    priority_weights: dict[str, float] = {}
    is_default: bool = False
    created_at: datetime | None = None


class Session(BaseModel):
    session_id: str = ""
    user_id: str = ""
    organization_id: str = ""
    status: str = "active"
    started_at: datetime | None = None
    metadata: dict[str, Any] = {}
    memory_count: int = 0
    created_at: datetime | None = None
    ended_at: datetime | None = None


class FeedbackResult(BaseModel):
    status: str = "success"
    memory_id: str = ""
    utility_score: float = 0.0
    confidence: float = 0.0
    memory_state: str = ""


class ReflectResult(BaseModel):
    status: str = "success"
    user_id: str = ""
    contradictions_detected: int = 0
    contradictions_resolved: int = 0
    patterns_consolidated: int = 0
    consolidated_patterns: list[dict[str, Any]] = []

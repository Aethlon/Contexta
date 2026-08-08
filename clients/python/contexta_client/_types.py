from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class contextaError(Exception):
    pass


class AuthenticationError(contextaError):
    pass


class AuthorizationError(contextaError):
    pass


class ValidationError(contextaError):
    def __init__(self, message: str, fields: Optional[List[Dict[str, str]]] = None) -> None:
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
    status: str
    estimated_processing_seconds: int = 0


class BatchObserveResponse(BaseModel):
    jobs: List[ObserveResponse] = []


class ScoreBreakdown(BaseModel):
    semantic: float = 0.0
    graph: float = 0.0
    importance: float = 0.0
    recency: float = 0.0
    keyword: float = 0.0


class ScoredMemory(BaseModel):
    memory_id: str
    memory_type: str = ""
    title: str = ""
    content: str = ""
    score: float = 0.0
    score_breakdown: Optional[ScoreBreakdown] = None
    tags: List[str] = []
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = {}


class TokenUsage(BaseModel):
    total: int = 0
    by_section: Dict[str, int] = {}


class ContextSection(BaseModel):
    title: str = ""
    content: str = ""
    tokens: int = 0


class UserProfile(BaseModel):
    user_id: str = ""
    name: str = ""
    preferences: List[str] = []
    traits: Dict[str, Any] = {}


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
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = {}


class Context(BaseModel):
    user_profile: Optional[UserProfile] = None
    active_projects: List[Project] = []
    preferences: List[Preference] = []
    goals: List[Goal] = []
    recent_events: List[Event] = []
    relevant_memories: List[ScoredMemory] = []
    token_usage: Optional[TokenUsage] = None
    cache_hit: bool = False
    request_id: str = ""


class Memory(BaseModel):
    memory_id: str
    memory_type: str = ""
    title: str = ""
    content: str = ""
    is_pinned: bool = False
    is_archived: bool = False
    tags: List[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Dict[str, Any] = {}


class Explanation(BaseModel):
    memory_id: str
    memory: Optional[Memory] = None
    extraction_source: Dict[str, Any] = {}
    classification_reasoning: str = ""
    scoring_breakdown: Optional[ScoreBreakdown] = None
    supersession_history: List[Dict[str, Any]] = []
    created_at: Optional[datetime] = None


class TimelineEvent(BaseModel):
    event_id: str = ""
    event_type: str = ""
    memory_id: str = ""
    description: str = ""
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = {}


class FieldDef(BaseModel):
    name: str
    type: str
    required: bool = False
    values: Optional[List[str]] = None
    description: str = ""


class Schema(BaseModel):
    schema_id: str = ""
    name: str
    field_definitions: List[FieldDef] = []
    created_at: Optional[datetime] = None


class Policy(BaseModel):
    policy_id: str = ""
    name: str
    store_rules: List[Dict[str, Any]] = []
    ignore_rules: List[Dict[str, Any]] = []
    priority_weights: Dict[str, float] = {}
    is_default: bool = False
    created_at: Optional[datetime] = None


class Session(BaseModel):
    session_id: str = ""
    user_id: str = ""
    status: str = "active"
    metadata: Dict[str, Any] = {}
    created_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

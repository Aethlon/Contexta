"""Contexta Python SDK.

The canonical entry points are :class:`Contexta` and :class:`AsyncContexta`. The
historical lowercase names ``contexta`` and ``Asynccontexta`` still resolve but
raise a ``DeprecationWarning`` and will be removed in a future major release.
"""

from __future__ import annotations

import warnings
from typing import Any

from contexta_client._context_builder import Context
from contexta_client._types import (
    AuthenticationError,
    AuthorizationError,
    BatchObserveResponse,
    ConflictError,
    ContextSection,
    DeleteResult,
    Event,
    Explanation,
    FeedbackResult,
    FieldDef,
    Goal,
    Memory,
    MemoryFlag,
    MemoryListEntry,
    NotFoundError,
    ObserveResponse,
    Policy,
    Preference,
    Project,
    QuotaExceeded,
    RateLimited,
    ReflectResult,
    Schema,
    ScoreBreakdown,
    ScoredMemory,
    ServerError,
    Session,
    TimelineEvent,
    TimelineResponse,
    TokenUsage,
    UserProfile,
    ValidationError,
    ValidationErrorDetail,
    contextaError,
)
from contexta_client.async_client import AsyncContexta
from contexta_client.client import Contexta

__version__ = "0.2.0"

__all__ = [
    "AsyncContexta",
    "Asynccontexta",
    "AuthenticationError",
    "AuthorizationError",
    "BatchObserveResponse",
    "ConflictError",
    "Context",
    "ContextSection",
    "Contexta",
    "DeleteResult",
    "Event",
    "Explanation",
    "FeedbackResult",
    "FieldDef",
    "Goal",
    "Memory",
    "MemoryFlag",
    "MemoryListEntry",
    "NotFoundError",
    "ObserveResponse",
    "Policy",
    "Preference",
    "Project",
    "QuotaExceeded",
    "RateLimited",
    "ReflectResult",
    "Schema",
    "ScoreBreakdown",
    "ScoredMemory",
    "ServerError",
    "Session",
    "TimelineEvent",
    "TimelineResponse",
    "TokenUsage",
    "UserProfile",
    "ValidationError",
    "ValidationErrorDetail",
    "contexta",
    "contextaError",
]

_DEPRECATED_ALIASES = {
    "contexta": (Contexta, "contexta"),
    "Asynccontexta": (AsyncContexta, "Asynccontexta"),
}


def __getattr__(name: str) -> Any:
    entry = _DEPRECATED_ALIASES.get(name)
    if entry is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    target, alias = entry
    warnings.warn(
        f"contexta_client.{alias} is deprecated and will be removed in a future "
        f"major release; use contexta_client.{target.__name__} instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return target

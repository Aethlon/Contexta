"""Retrieval API routes."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.core.retrieval.agentic_engine import AgenticRetrievalEngine
from contexta.core.retrieval.engine import RetrievalEngine
from contexta.core.schemas import RetrievalQuery
from contexta.db import get_db_session
from contexta.repositories.entity_repo import (
    EntityEdgeRepository,
    EntityRepository,
    MemoryEntityLinkRepository,
)
from contexta.repositories.memory_repo import MemoryRepository
from contexta.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)
router = APIRouter()

_SCOPE_HEADERS = {
    "memory_user_id": (
        "x-memory-user-id",
        "x-contexta-memory-user-id",
        "X-Mem-Memory-User-Id",
    ),
    "agent_id": (
        "x-agent-id",
        "x-contexta-agent-id",
        "X-Mem-Agent-Id",
        "x-mem-agent-id",
    ),
    "project_id": (
        "x-project-id",
        "x-contexta-project-id",
        "X-Mem-Project-Id",
        "x-mem-project-id",
    ),
    "session_id": (
        "x-session-id",
        "x-contexta-session-id",
        "X-Mem-Session-Id",
        "x-mem-session-id",
    ),
}
_SCOPE_QUERY_NAMES = {
    "memory_user_id": ("memory_user_id",),
    "agent_id": ("agent_id",),
    "project_id": ("project_id",),
    "session_id": ("session_id",),
}


class ScopedRetrievalQuery(RetrievalQuery):
    user_id: UUID | None = None
    memory_user_id: UUID | None = None
    organization_id: UUID | None = None
    agent_id: str | UUID | None = Field(default=None, min_length=1, max_length=255)
    project_id: str | UUID | None = Field(default=None, min_length=1, max_length=255)
    session_id: UUID | None = None


class BatchRetrievalQuery(BaseModel):
    queries: list[ScopedRetrievalQuery]


class InvestigateRetrievalQuery(BaseModel):
    query_text: str = Field(..., min_length=1)
    user_id: UUID | None = None
    memory_user_id: UUID | None = None
    organization_id: UUID | None = None
    agent_id: str | UUID | None = Field(default=None, min_length=1, max_length=255)
    project_id: str | UUID | None = Field(default=None, min_length=1, max_length=255)
    session_id: UUID | None = None
    max_hops: int = Field(default=2, ge=0, le=5)
    limit: int = Field(default=15, gt=0, le=100)


@dataclass(frozen=True)
class _RetrievalScope:
    organization_id: UUID
    user_id: UUID
    memory_user_id: str | None
    agent_id: str | None
    project_id: str | None
    session_id: UUID | None


@dataclass
class _ScopeState:
    memory_ids: set[UUID] = field(default_factory=set)
    entity_ids: set[UUID] = field(default_factory=set)


def _as_uuid(value: Any, field: str) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field} must be a UUID.",
        ) from exc


def _try_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _state_uuid(request: Request, field: str) -> UUID | None:
    value = getattr(request.state, field, None)
    try:
        return _as_uuid(value, field)
    except HTTPException as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated tenant context is invalid.",
        ) from exc


def _verified_identity(request: Request) -> bool:
    state = request.state
    return bool(
        getattr(state, "auth_verified", False)
        or (
            getattr(state, "authenticated", False)
            and getattr(state, "api_key_id", None)
        )
    )


def _compatibility_identity(request: Request) -> bool:
    state = request.state
    return bool(
        getattr(state, "auth_compatibility", False)
        or (
            getattr(state, "authenticated", False)
            and not getattr(state, "auth_verified", False)
            and not getattr(state, "api_key_id", None)
        )
    )


def _reject_identity_mismatch(
    field: str,
    supplied: UUID | None,
    authoritative: UUID | None,
) -> None:
    if supplied is not None and authoritative is not None and supplied != authoritative:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: {field} does not match authenticated identity.",
        )


def _resolve_identity(
    request: Request,
    organization_id: Any,
    user_id: Any,
) -> tuple[UUID, UUID]:
    supplied_org = _as_uuid(organization_id, "organization_id")
    supplied_user = _as_uuid(user_id, "user_id")
    state_org = _state_uuid(request, "organization_id")
    state_actor = _state_uuid(request, "actor_id")

    if _verified_identity(request):
        if state_org is None or state_actor is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authenticated tenant context is invalid.",
            )
        _reject_identity_mismatch("organization_id", supplied_org, state_org)
        _reject_identity_mismatch("user_id", supplied_user, state_actor)
        return state_org, state_actor

    if getattr(request.state, "auth_test_fallback", False) and not getattr(
        request.state,
        "auth_header_present",
        False,
    ):
        if supplied_org is None or supplied_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
            )
        return supplied_org, supplied_user

    if _compatibility_identity(request):
        _reject_identity_mismatch("organization_id", supplied_org, state_org)
        _reject_identity_mismatch("user_id", supplied_user, state_actor)
        if state_org is None or state_actor is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
            )
        return state_org, state_actor

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
    )


def _scope_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = _try_uuid(text)
    return str(normalized) if normalized is not None else text


def _header_value(request: Request, names: tuple[str, ...], field: str) -> str | None:
    values: set[str] = set()
    for name in names:
        for value in request.headers.getlist(name):
            normalized = _scope_text(value)
            if normalized is not None:
                values.add(normalized)
    if not values:
        return None
    if len(values) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} headers disagree.",
        )
    return next(iter(values))


def _query_value(request: Request, names: tuple[str, ...], field: str) -> str | None:
    values: set[str] = set()
    for name in names:
        for value in request.query_params.getlist(name):
            normalized = _scope_text(value)
            if normalized is not None:
                values.add(normalized)
    if not values:
        return None
    if len(values) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} query parameters disagree.",
        )
    return next(iter(values))


def _scope_value(
    request: Request,
    payload: Any,
    field: str,
) -> str | None:
    values: list[str] = []
    body_value = _scope_text(getattr(payload, field, None))
    if body_value is not None:
        values.append(body_value)
    header_value = _header_value(request, _SCOPE_HEADERS[field], field)
    if header_value is not None:
        values.append(header_value)
    query_value = _query_value(request, _SCOPE_QUERY_NAMES[field], field)
    if query_value is not None:
        values.append(query_value)
    state_value = _scope_text(getattr(request.state, field, None))
    if state_value is not None:
        values.append(state_value)
    if len(set(values)) > 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: {field} does not match authenticated scope.",
        )
    return values[0] if values else None


def _scope_for(request: Request, payload: Any) -> _RetrievalScope:
    organization_id, user_id = _resolve_identity(
        request,
        getattr(payload, "organization_id", None),
        getattr(payload, "user_id", None),
    )
    session_value = _scope_value(request, payload, "session_id")
    session_id = _as_uuid(session_value, "session_id") if session_value is not None else None
    return _RetrievalScope(
        organization_id=organization_id,
        user_id=user_id,
        memory_user_id=_scope_value(request, payload, "memory_user_id"),
        agent_id=_scope_value(request, payload, "agent_id"),
        project_id=_scope_value(request, payload, "project_id"),
        session_id=session_id,
    )


def _authoritative_query(query: Any, scope: _RetrievalScope) -> Any:
    return query.model_copy(
        update={
            "organization_id": scope.organization_id,
            "user_id": scope.user_id,
            "memory_user_id": scope.memory_user_id,
            "agent_id": scope.agent_id,
            "project_id": scope.project_id,
            "session_id": scope.session_id,
        }
    )


def _memory_value(memory: Any, field: str) -> Any:
    if isinstance(memory, Mapping):
        return memory.get(field)
    return getattr(memory, field, None)


def _add_scope_value(values: set[str], value: Any) -> None:
    if value is None:
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _add_scope_value(values, item)
        return
    if isinstance(value, Mapping):
        for key in ("id", "agent_id", "project_id", "session_id", "agent", "project", "session"):
            if key in value:
                _add_scope_value(values, value[key])
        return
    text = _scope_text(value)
    if text is not None:
        values.add(text)


def _has_scope_field(container: Any, field: str) -> bool:
    short_field = field.removesuffix("_id")
    if isinstance(container, Mapping):
        return field in container or short_field in container
    return hasattr(container, field) or hasattr(container, short_field)


def _scope_source(container: Any, field: str) -> tuple[set[str], set[str]]:
    explicit: set[str] = set()
    fallback: set[str] = set()
    short_field = field.removesuffix("_id")
    found = False
    if isinstance(container, Mapping):
        for key in (field, short_field):
            if key in container:
                found = True
                _add_scope_value(explicit, container[key])
    else:
        for key in (field, short_field):
            value = getattr(container, key, None)
            if value is not None:
                found = True
                _add_scope_value(explicit, value)
    if found:
        return explicit, fallback
    if isinstance(container, Mapping):
        if "id" in container:
            _add_scope_value(fallback, container["id"])
    else:
        _add_scope_value(fallback, getattr(container, "id", None))
    return set(), fallback


def _memory_scope_sources(memory: Any, field: str) -> tuple[list[set[str]], set[str]]:
    sources: list[set[str]] = []
    fallback: set[str] = set()
    direct = _memory_value(memory, field)
    if _has_scope_field(memory, field):
        values: set[str] = set()
        _add_scope_value(values, direct)
        sources.append(values)
    structured = _memory_value(memory, "structured_data")
    if isinstance(structured, Mapping):
        values, generic = _scope_source(structured, field)
        if _has_scope_field(structured, field):
            sources.append(values)
        fallback.update(generic)
        for container_name in ("scope", "metadata", "context", "attributes"):
            values, generic = _scope_source(structured.get(container_name), field)
            if _has_scope_field(structured.get(container_name), field):
                sources.append(values)
            fallback.update(generic)
    for container_name in ("scope", "metadata", "context", "attributes"):
        values, generic = _scope_source(_memory_value(memory, container_name), field)
        if _has_scope_field(_memory_value(memory, container_name), field):
            sources.append(values)
        fallback.update(generic)
    prefixes = (f"{field.removesuffix('_id')}:", f"{field}:")
    tags = _memory_value(memory, "tags") or []
    if isinstance(tags, str):
        tags = [tags]
    tag_values: set[str] = set()
    for tag in tags:
        tag_text = str(tag)
        for prefix in prefixes:
            if tag_text.startswith(prefix):
                tag_values.add(_scope_text(tag_text[len(prefix) :]) or "")
    if tag_values:
        sources.append(tag_values)
    return sources, fallback


def _memory_scope_values(memory: Any, field: str) -> set[str]:
    sources, fallback = _memory_scope_sources(memory, field)
    values = set(fallback)
    for source in sources:
        values.update(source)
    values.discard("")
    return values


def _memory_scope_matches(memory: Any, field: str, requested: str) -> bool:
    sources, fallback = _memory_scope_sources(memory, field)
    if sources:
        return all(requested in source for source in sources)
    return requested in fallback


def _memory_in_scope(memory: Any, scope: _RetrievalScope) -> bool:
    if memory is None:
        return False
    try:
        organization_id = _try_uuid(_memory_value(memory, "organization_id"))
        user_id = _try_uuid(_memory_value(memory, "user_id"))
        if organization_id != scope.organization_id or user_id != scope.user_id:
            return False
        for field, requested in (
            ("memory_user_id", scope.memory_user_id),
            ("agent_id", scope.agent_id),
            ("project_id", scope.project_id),
            ("session_id", str(scope.session_id) if scope.session_id is not None else None),
        ):
            if requested is not None and not _memory_scope_matches(memory, field, requested):
                return False
        return True
    except (AttributeError, TypeError, ValueError):
        return False


def _value_sequence(value: Any) -> list[Any]:
    if value is None or isinstance(value, (str, bytes)):
        return []
    if isinstance(value, Mapping):
        return [value]
    try:
        return list(value)
    except (TypeError, ValueError):
        return [value]


def _filter_records(records: Any, scope: _RetrievalScope) -> list[Any]:
    return [
        record
        for record in _value_sequence(records)
        if _memory_in_scope(record, scope)
    ]


def _filter_results(results: Any, scope: _RetrievalScope) -> list[Any]:
    return [
        result
        for result in _value_sequence(results)
        if _memory_in_scope(getattr(result, "memory", None), scope)
    ]


def _record_id(value: Any) -> UUID | None:
    return _try_uuid(value)


def _record_ids(records: list[Any]) -> set[UUID]:
    identifiers: set[UUID] = set()
    for record in records:
        identifier = _record_id(_memory_value(record, "id"))
        if identifier is not None:
            identifiers.add(identifier)
    return identifiers


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class _ScopedMemoryRepository:
    _READ_METHODS = frozenset(
        {
            "get_all",
            "get_by_id",
            "get_by_user",
            "get_by_vector_similarity",
            "get_by_lexical_similarity",
            "get_by_session",
            "get_many_by_ids",
            "get_current_truths",
            "get_by_type",
            "get_by_state",
            "get_unpinned_by_state",
        }
    )

    def __init__(
        self,
        repository: Any,
        scope: _RetrievalScope,
        state: _ScopeState,
    ) -> None:
        self._repository = repository
        self._scope = scope
        self._state = state

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._repository, name)
        if name in {"touch_accessed", "touch_accessed_many"} and callable(target):

            async def touch(*args: Any, **kwargs: Any) -> Any:
                if name == "touch_accessed":
                    raw_id = args[0] if args else kwargs.get("record_id")
                    identifier = _record_id(raw_id)
                    if identifier is None or identifier not in self._state.memory_ids:
                        return 0
                    call_args = (identifier, *args[1:])
                    call_kwargs = dict(kwargs)
                    call_kwargs.pop("record_id", None)
                    return await _await_if_needed(target(*call_args, **call_kwargs))

                raw_ids = args[0] if args else kwargs.get("record_ids", ())
                identifiers: list[UUID] = []
                for value in _value_sequence(raw_ids):
                    identifier = _record_id(value)
                    if identifier is not None and identifier in self._state.memory_ids:
                        identifiers.append(identifier)
                if not identifiers:
                    return 0
                call_args = (identifiers, *args[1:])
                call_kwargs = dict(kwargs)
                call_kwargs.pop("record_ids", None)
                return await _await_if_needed(target(*call_args, **call_kwargs))

            return touch
        if name not in self._READ_METHODS or not callable(target):
            return target

        async def filtered(*args: Any, **kwargs: Any) -> Any:
            result = await _await_if_needed(target(*args, **kwargs))
            safe = _filter_records(result, self._scope)
            self._state.memory_ids.update(_record_ids(safe))
            return safe

        return filtered


class _ScopedEntityRepository:
    _READ_METHODS = frozenset(
        {
            "get_all",
            "get_by_id",
            "get_by_user",
            "get_by_type",
            "get_by_name",
            "get_by_names",
        }
    )

    def __init__(
        self,
        repository: Any,
        scope: _RetrievalScope,
        state: _ScopeState,
    ) -> None:
        self._repository = repository
        self._scope = scope
        self._state = state

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._repository, name)
        if name not in self._READ_METHODS or not callable(target):
            return target

        async def filtered(*args: Any, **kwargs: Any) -> Any:
            supplied_user = kwargs.get("user_id")
            if supplied_user is None and name in {
                "get_by_user",
                "get_by_type",
                "get_by_name",
                "get_by_names",
            }:
                supplied_user = args[0] if args else None
            if supplied_user is not None:
                parsed_user = _try_uuid(supplied_user)
                if parsed_user is None or parsed_user != self._scope.user_id:
                    return []
            result = await _await_if_needed(target(*args, **kwargs))
            records = [
                record
                for record in _value_sequence(result)
                if _try_uuid(_memory_value(record, "organization_id")) == self._scope.organization_id
                and _try_uuid(_memory_value(record, "user_id")) == self._scope.user_id
            ]
            self._state.entity_ids.update(_record_ids(records))
            return records

        return filtered


class _ScopedLinkRepository:
    _READ_METHODS = frozenset(
        {
            "get_entities_for_memory",
            "bulk_get_entities_for_memories",
            "get_memories_for_entity",
            "bulk_get_memories_for_entities",
        }
    )

    def __init__(
        self,
        repository: Any,
        scope: _RetrievalScope,
        state: _ScopeState,
        memory_repository: Any | None = None,
        entity_repository: Any | None = None,
    ) -> None:
        self._repository = repository
        self._scope = scope
        self._state = state
        self._memory_repository = memory_repository
        self._entity_repository = entity_repository

    async def _memory_allowed(self, identifier: UUID | None) -> bool:
        if identifier is None:
            return False
        if identifier in self._state.memory_ids:
            return True
        resolver = getattr(self._memory_repository, "get_by_id", None)
        if not callable(resolver):
            return False
        await resolver(identifier)
        return identifier in self._state.memory_ids

    async def _entity_allowed(self, identifier: UUID | None) -> bool:
        if identifier is None:
            return False
        if identifier in self._state.entity_ids:
            return True
        resolver = getattr(self._entity_repository, "get_by_id", None)
        if not callable(resolver):
            return False
        await resolver(identifier)
        return identifier in self._state.entity_ids

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._repository, name)
        if name not in self._READ_METHODS or not callable(target):
            return target

        async def filtered(*args: Any, **kwargs: Any) -> Any:
            call_args = list(args)
            call_kwargs = dict(kwargs)
            if name in {"get_entities_for_memory", "bulk_get_entities_for_memories"}:
                raw_ids = call_args[0] if call_args else call_kwargs.get(
                    "memory_ids" if name == "bulk_get_entities_for_memories" else "memory_id"
                )
                if name == "get_entities_for_memory":
                    raw_ids = (raw_ids,)
                safe_ids: list[UUID] = []
                for value in _value_sequence(raw_ids):
                    identifier = _record_id(value)
                    if await self._memory_allowed(identifier) and identifier not in safe_ids:
                        safe_ids.append(identifier)
                if not safe_ids:
                    return []
                if name == "bulk_get_entities_for_memories":
                    call_args[0] = safe_ids
                    call_kwargs.pop("memory_ids", None)
                else:
                    call_args[0] = safe_ids[0]
                    call_kwargs.pop("memory_id", None)
            elif name in {"get_memories_for_entity", "bulk_get_memories_for_entities"}:
                raw_ids = call_args[0] if call_args else call_kwargs.get(
                    "entity_ids" if name == "bulk_get_memories_for_entities" else "entity_id"
                )
                if name == "get_memories_for_entity":
                    raw_ids = (raw_ids,)
                safe_ids = []
                for value in _value_sequence(raw_ids):
                    identifier = _record_id(value)
                    if await self._entity_allowed(identifier) and identifier not in safe_ids:
                        safe_ids.append(identifier)
                if not safe_ids:
                    return []
                if name == "bulk_get_memories_for_entities":
                    call_args[0] = safe_ids
                    call_kwargs.pop("entity_ids", None)
                else:
                    call_args[0] = safe_ids[0]
                    call_kwargs.pop("entity_id", None)
            result = await _await_if_needed(target(*call_args, **call_kwargs))
            records = []
            for record in _value_sequence(result):
                organization_id = _try_uuid(_memory_value(record, "organization_id"))
                memory_id = _record_id(_memory_value(record, "memory_id"))
                entity_id = _record_id(_memory_value(record, "entity_id"))
                if (
                    organization_id == self._scope.organization_id
                    and await self._memory_allowed(memory_id)
                    and await self._entity_allowed(entity_id)
                ):
                    records.append(record)
            return records

        return filtered


class _ScopedEdgeRepository:
    _READ_METHODS = frozenset(
        {
            "get_edges_from",
            "get_edges_to",
            "get_neighbors",
            "bulk_get_neighbors",
            "get_existing_edges",
        }
    )

    def __init__(
        self,
        repository: Any,
        scope: _RetrievalScope,
        state: _ScopeState,
        entity_repository: Any | None = None,
    ) -> None:
        self._repository = repository
        self._scope = scope
        self._state = state
        self._entity_repository = entity_repository

    async def _entity_allowed(self, identifier: UUID | None) -> bool:
        if identifier is None:
            return False
        if identifier in self._state.entity_ids:
            return True
        resolver = getattr(self._entity_repository, "get_by_id", None)
        if not callable(resolver):
            return False
        await resolver(identifier)
        return identifier in self._state.entity_ids

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._repository, name)
        if name not in self._READ_METHODS or not callable(target):
            return target

        async def filtered(*args: Any, **kwargs: Any) -> Any:
            raw_id = args[0] if args else kwargs.get("entity_id")
            identifier = _record_id(raw_id)
            if not await self._entity_allowed(identifier):
                return []
            result = await _await_if_needed(target(*args, **kwargs))
            records = []
            for record in _value_sequence(result):
                organization_id = _try_uuid(_memory_value(record, "organization_id"))
                source_id = _record_id(_memory_value(record, "source_entity_id"))
                target_id = _record_id(_memory_value(record, "target_entity_id"))
                if (
                    organization_id == self._scope.organization_id
                    and await self._entity_allowed(source_id)
                    and await self._entity_allowed(target_id)
                ):
                    records.append(record)
            return records

        return filtered


def _retrieval_engine(
    session: AsyncSession,
    scope: _RetrievalScope,
) -> tuple[RetrievalEngine, Any, Any]:
    state = _ScopeState()
    memory_repository = _ScopedMemoryRepository(
        MemoryRepository(session, tenant_id=scope.organization_id),
        scope,
        state,
    )
    entity_repository = _ScopedEntityRepository(
        EntityRepository(session, tenant_id=scope.organization_id),
        scope,
        state,
    )
    link_repository = _ScopedLinkRepository(
        MemoryEntityLinkRepository(session, tenant_id=scope.organization_id),
        scope,
        state,
        memory_repository=memory_repository,
        entity_repository=entity_repository,
    )
    edge_repository = _ScopedEdgeRepository(
        EntityEdgeRepository(session, tenant_id=scope.organization_id),
        scope,
        state,
        entity_repository=entity_repository,
    )
    engine = RetrievalEngine(
        memory_repository=memory_repository,
        link_repository=link_repository,
        edge_repository=edge_repository,
        entity_repository=entity_repository,
    )
    return engine, entity_repository, edge_repository


# Bitemporal and fact-identity columns every retrieval response must carry.
# `MemoryRecord` mixes naive `DateTime` columns (`valid_from`, `valid_to`,
# `last_accessed_at`) with `TIMESTAMPTZ` ones (`event_at`, `observed_at`), so
# nothing here may assume an offset is attached.
_BITEMPORAL_DATETIME_FIELDS = (
    "valid_from",
    "valid_to",
    "event_at",
    "observed_at",
    "last_accessed_at",
)
_TEMPORAL_TEXT_FIELDS = (
    "temporal_precision",
    "temporal_basis",
    "fact_key",
)
_CHANNEL_NAMES = ("dense", "lexical", "graph")


def _iso_or_none(value: Any) -> str | None:
    """ISO-8601 for any datetime, naive or tz-aware; `None` stays `None`.

    `isoformat()` is total over both kinds of datetime, so a naive
    `valid_from` serialises exactly as well as an aware `event_at`. The guard
    only stops an unexpected value from turning a debug field into a 500.
    """
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        with suppress(Exception):
            return isoformat()
    return str(value)


def _text_or_none(value: Any) -> str | None:
    """String or `None`, never a bare non-string where a string is expected."""
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _is_current(memory: Any) -> bool:
    """One derivation of currentness, shared by every serialiser.

    A row is current when nothing has closed its validity interval. The agentic
    serialiser already derived it this way inline; both now call this so the two
    responses can never disagree about whether a fact is open.
    """
    return _memory_value(memory, "valid_to") is None


def _memory_temporal_payload(memory: Any) -> dict[str, Any]:
    """Bitemporal and fact-identity fields for one memory.

    Always every key, with `None` where the column is null: a caller debugging
    supersession needs to see `valid_to: null` (still open) as clearly as
    `valid_to: "2026-01-01T00:00:00"` (closed), and `fact_key` because that is
    the identity the truth engine uses to decide whether two rows are the same
    fact.
    """
    payload: dict[str, Any] = {
        name: _iso_or_none(getattr(memory, name, None))
        for name in _BITEMPORAL_DATETIME_FIELDS
    }
    payload.update(
        {
            name: _text_or_none(getattr(memory, name, None))
            for name in _TEMPORAL_TEXT_FIELDS
        }
    )
    payload["is_current"] = _is_current(memory)
    return payload


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_int(value: Any) -> int | None:
    # `bool` is an `int` subclass, so it is rejected before the int check.
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_text_list(value: Any) -> list[str] | None:
    if not isinstance(value, (list, tuple)):
        return None
    return [item for item in value if isinstance(item, str)]


def _coerce_weights(value: Any) -> dict[str, float] | None:
    """The three channel weights, or `None` if `value` is not a weight mapping.

    Every channel must be present and numeric. A partial or non-numeric mapping
    is reported as unavailable rather than half-reported, so the caller never
    sees a weights block that implies a channel was left at zero.
    """
    if not isinstance(value, Mapping):
        return None
    weights: dict[str, float] = {}
    for name in _CHANNEL_NAMES:
        weight = value.get(name)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            return None
        weights[name] = float(weight)
    return weights


def _effective_channel_weights(engine: Any) -> dict[str, float] | None:
    """The weights the engine's RRF pass actually fused with.

    `RetrievalEngine._channel_weights` is the engine's own accessor for the
    weights in force (it boosts one channel when the cortex classifies the
    query), so it is preferred over the class default, which is only the
    starting point. Both are read defensively: a test double must degrade to
    `None` rather than leak a `Mock` into a JSON response.
    """
    resolver = getattr(engine, "_channel_weights", None)
    if callable(resolver):
        weights = None
        with suppress(Exception):
            weights = _coerce_weights(resolver(None))
        if weights is not None:
            return weights
    for source in (engine, RetrievalEngine):
        weights = _coerce_weights(getattr(source, "DEFAULT_CHANNEL_WEIGHTS", None))
        if weights is not None:
            return weights
    return None


def _sufficiency_payload(assessment: Any) -> dict[str, Any] | None:
    """The gate's verdict, or `None` when the engine recorded no assessment."""
    if assessment is None:
        return None
    return {
        "sufficient": _optional_bool(getattr(assessment, "sufficient", None)),
        "reason": _optional_text(getattr(assessment, "reason", None)),
        "result_count": _optional_int(getattr(assessment, "result_count", None)),
        "required_result_count": _optional_int(
            getattr(assessment, "required_result_count", None)
        ),
        "covered_entities": _optional_text_list(
            getattr(assessment, "covered_entities", None)
        ),
        "required_entities": _optional_text_list(
            getattr(assessment, "required_entities", None)
        ),
        "missing_evidence_ids": _optional_text_list(
            getattr(assessment, "missing_evidence_ids", None)
        ),
        "top_score": _optional_float(getattr(assessment, "top_score", None)),
        "runner_up_score": _optional_float(getattr(assessment, "runner_up_score", None)),
        "margin": _optional_float(getattr(assessment, "margin", None)),
    }


def _channel_diagnostics(engine: Any, *, returned_results: int) -> dict[str, Any]:
    """Per-channel observability for one retrieval.

    Everything reported here is read off `RetrievalEngine.last_escalation`,
    which the engine sets once per `retrieve()`. The route builds a fresh engine
    per request, so reading it after the call is race-free.

    A candidate count is reported only when the engine recorded a real one. The
    engine tracks only `dense_candidates`; lexical and graph counts are not
    exposed anywhere, so they are emitted as `null` and listed in
    `unavailable_candidate_counts` rather than guessed or derived. That
    distinction is the whole point of the block: `0` means the channel was
    measured, `null` means it was never measured, and RRF silently drops a
    zero-candidate channel and renormalises the remaining weights over it
    (`weighted_reciprocal_rank_fusion`, fusion.py), so a three-layer request can
    quietly answer from two.

    `dense: 0` is ambiguous on its own and must be read with
    `dense_escalation.escalated`: it is 0 both when dense was never consulted
    (cascade enabled and the gate said lexical + graph sufficed) and when it was
    consulted and matched nothing (escalation disabled, so dense always runs).

    `returned_results` is post-tenant-filter, so it separates "the engine found
    nothing" from "the scope filter dropped everything the engine found".
    """
    escalation = getattr(engine, "last_escalation", None)
    candidates: dict[str, int | None] = {
        name: _optional_int(getattr(escalation, f"{name}_candidates", None))
        for name in _CHANNEL_NAMES
    }
    return {
        "weights": _effective_channel_weights(engine),
        "candidates": candidates,
        "unavailable_candidate_counts": [
            name for name, count in candidates.items() if count is None
        ],
        "fused_candidates": _optional_int(
            getattr(escalation, "fused_candidates", None)
        ),
        "returned_results": returned_results,
        "dense_escalation": {
            "enabled": _optional_bool(getattr(escalation, "enabled", None)),
            "escalated": _optional_bool(getattr(escalation, "escalated", None)),
            "reason": _optional_text(getattr(escalation, "reason", None)),
            "sufficiency": _sufficiency_payload(
                getattr(escalation, "assessment", None)
            ),
        },
    }


def _serialize_result(item: Any) -> dict[str, Any]:
    memory = item.memory
    return {
        "memory": {
            "id": str(memory.id),
            "user_id": str(memory.user_id),
            "organization_id": str(memory.organization_id),
            "memory_type": memory.memory_type,
            "title": memory.title,
            "content": memory.content,
            "structured_data": memory.structured_data,
            "tags": memory.tags,
            "is_pinned": memory.is_pinned,
            "is_archived": memory.is_archived,
            "memory_state": memory.memory_state,
            "created_at": memory.created_at.isoformat() if memory.created_at else None,
            **_memory_temporal_payload(memory),
        },
        "score": item.score,
        "semantic_score": item.semantic_score,
        "graph_score": item.graph_score,
        "importance_score": item.importance_score,
        "recency_score": item.recency_score,
        "keyword_score": item.keyword_score,
    }


@router.post("/retrieve")
async def retrieve(
    request: Request,
    query: ScopedRetrievalQuery,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Retrieve memories using hybrid semantic, keyword, recency, importance, and graph scoring.

    The response carries a top-level `channels` block with the per-channel
    candidate counts, the weights that were fused, and the dense-escalation
    decision, so a caller can see which of the three retrieval layers actually
    contributed instead of inferring it from the ranking.
    """
    scope = _scope_for(request, query)
    scoped_query = _authoritative_query(query, scope)
    embedding_service = EmbeddingService()
    query_embedding = None
    with suppress(Exception):
        query_embedding = await embedding_service.embed_text(query.query_text)
    if query_embedding is None:
        logger.warning("Query embedding generation failed, falling back to non-semantic scoring")

    engine, _, _ = _retrieval_engine(session, scope)
    results = await engine.retrieve(scoped_query, query_embedding=query_embedding)
    serialized_results = [_serialize_result(item) for item in _filter_results(results, scope)]
    return {
        "status": "success",
        "query": query.query_text,
        "count": len(serialized_results),
        "channels": _channel_diagnostics(engine, returned_results=len(serialized_results)),
        "results": serialized_results,
    }


@router.post("/retrieve/batch")
async def retrieve_batch(
    request: Request,
    payload: BatchRetrievalQuery,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Concurrently execute multiple memory retrieval queries in parallel."""
    if not payload.queries:
        return {"status": "success", "count": 0, "batch_results": []}

    scopes = [_scope_for(request, query) for query in payload.queries]
    embedding_service = EmbeddingService()

    async def _safe_embed(query_text: str):
        with suppress(Exception):
            return await embedding_service.embed_text(query_text)
        return None

    query_embeddings = await asyncio.gather(
        *[_safe_embed(query.query_text) for query in payload.queries]
    )

    async def _execute_single(
        query: ScopedRetrievalQuery,
        query_embedding: list[float] | None,
        scope: _RetrievalScope,
    ):
        scoped_query = _authoritative_query(query, scope)
        engine, _, _ = _retrieval_engine(session, scope)
        results = await engine.retrieve(scoped_query, query_embedding=query_embedding)
        serialized = [_serialize_result(item) for item in _filter_results(results, scope)]
        return {
            "query": query.query_text,
            "count": len(serialized),
            "channels": _channel_diagnostics(engine, returned_results=len(serialized)),
            "results": serialized,
        }

    batch_results = []
    for query, embedding, scope in zip(payload.queries, query_embeddings, scopes):
        batch_results.append(await _execute_single(query, embedding, scope))
    return {
        "status": "success",
        "count": len(batch_results),
        "batch_results": batch_results,
    }


@router.post("/retrieve/investigate")
async def retrieve_investigate(
    payload: InvestigateRetrievalQuery,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Execute iterative agentic investigative retrieval (ASMR-style multi-hop memory reasoning)."""
    scope = _scope_for(request, payload)
    engine, entity_repository, edge_repository = _retrieval_engine(session, scope)
    agentic_engine = AgenticRetrievalEngine(
        retrieval_engine=engine,
        entity_repository=entity_repository,
        edge_repository=edge_repository,
    )

    embedding_service = EmbeddingService()
    query_embedding = None
    with suppress(Exception):
        query_embedding = await embedding_service.embed_text(payload.query_text)

    result = await agentic_engine.investigate(
        query_text=payload.query_text,
        user_id=scope.user_id,
        organization_id=scope.organization_id,
        max_hops=payload.max_hops,
        limit=payload.limit,
        query_embedding=query_embedding,
    )
    memories = _filter_results(getattr(result, "memories", []), scope)
    return {
        "status": "success",
        "query": result.query,
        "execution_time_ms": result.execution_time_ms,
        "entities_discovered": result.entities_discovered,
        "investigation_trace": [
            {
                "step": step.step_number,
                "action": step.action,
                "target": step.target,
                "rationale": step.rationale,
                "discovered_count": step.discovered_count,
            }
            for step in result.investigation_trace
        ],
        "temporal_evolution": result.temporal_evolution,
        "synthesized_context": result.synthesized_context,
        "results": [
            {
                "id": str(item.memory.id),
                "title": item.memory.title,
                "content": item.memory.content,
                "memory_type": item.memory.memory_type,
                "score": item.score,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                **_memory_temporal_payload(item.memory),
            }
            for item in memories
        ],
    }

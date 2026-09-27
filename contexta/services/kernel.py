from __future__ import annotations

import hashlib
import inspect
import json
import logging
import math
import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from contexta.contracts.context import (
    BuildContextRequest,
    ContextBlock,
    ContextBlockKind,
    ContextPackage,
    deserialize_context_package,
    serialize_context_package,
)
from contexta.contracts.runtime import (
    CANONICAL_WRITE_AUTHORITY,
    BlockUpdateProposal,
    CorrectionResult,
    CorrectRequest,
    EvidenceKind,
    EvidenceRef,
    ExplainRequest,
    ExplanationResult,
    GetOperationRequest,
    GraphDirection,
    GraphEdge,
    GraphNode,
    GraphSearchResult,
    LinkedMemory,
    MemoryHit,
    ObserveRequest,
    ObserveResult,
    OperationError,
    OperationKind,
    OperationResult,
    OperationStatus,
    ProposeBlockUpdateRequest,
    RecallRequest,
    RecallResult,
    Scope,
    SearchGraphRequest,
)
from contexta.core.context.builder import ContextBuilder
from contexta.core.context.context_package import ContextPackageBuilder as CoreContextPackageBuilder
from contexta.core.errors import contextaError
from contexta.core.pipeline import FastMemoryOrchestrator
from contexta.core.retrieval.engine import RetrievalEngine, RetrievalResult
from contexta.core.schemas import ContextConfig, ContextRequest, ObservationPayload, RetrievalQuery
from contexta.core.types import MemoryType
from contexta.models.memory import MemoryRecord
from contexta.repositories.entity_repo import (
    EntityEdgeRepository,
    EntityRepository,
    MemoryEntityLinkRepository,
)
from contexta.repositories.memory_repo import MemoryRepository
from contexta.services.embedding import EmbeddingService

SessionFactory = Callable[[], Any]
RetrievalEngineFactory = Callable[..., Any]


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return _safe(value.value)
    if isinstance(value, (datetime, UUID)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        with suppress(TypeError, ValueError):
            return _safe(value.model_dump(mode="json", by_alias=True))
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)


def _uuid(value: Any, name: str) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a UUID") from exc


def _optional_uuid(value: Any, field_name: str | None = None) -> UUID | None:
    """Parse an optional UUID, naming the offending field when it is malformed.

    Callers pass ``field_name`` so a bad scope value produces an actionable error
    instead of a bare ``TypeError`` deep inside retrieval.
    """
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        if field_name:
            raise ValueError(
                f"{field_name} must be a UUID, got {value!r}"
            ) from exc
        return None


def _memory_text(memory: Any) -> str:
    try:
        value = memory.plaintext_content
    except (AttributeError, TypeError, ValueError, RuntimeError):
        if isinstance(memory, MemoryRecord):
            return ""
        value = _field(memory, "content", "")
    return str(value or "")


def _memory_id(memory: Any) -> str:
    for name in ("memory_id", "id", "evidence_id"):
        value = _field(memory, name)
        if value is not None and str(value):
            return str(value)
    title = str(_field(memory, "title", "") or "")
    content = _memory_text(memory)
    digest = hashlib.sha256(f"{title}\0{content}".encode()).hexdigest()
    return f"memory:{digest}"


def _source_values(memory: Any) -> list[str]:
    values: list[Any] = []
    for name in ("source_id", "source_message_id", "observation_id", "source_ids"):
        value = _field(memory, name)
        if isinstance(value, (list, tuple, set)):
            values.extend(value)
        elif value is not None:
            values.append(value)
    structured = _field(memory, "structured_data")
    if isinstance(structured, Mapping):
        for name in ("source_id", "source_message_id", "observation_id", "source_ids"):
            value = structured.get(name)
            if isinstance(value, (list, tuple, set)):
                values.extend(value)
            elif value is not None:
                values.append(value)
    return list(dict.fromkeys(str(value) for value in values if value is not None and str(value)))


def _memory_evidence(memory: Any, *, include_excerpt: bool = True) -> EvidenceRef:
    identifier = _memory_id(memory)
    source_ids = _source_values(memory)
    metadata = {
        "memory_type": _safe(_field(memory, "memory_type")),
        "source_type": _safe(_field(memory, "source_type")),
        "importance": _safe(_field(memory, "importance", 0.0)),
        "confidence": _safe(_field(memory, "confidence", 0.0)),
        "valid_from": _safe(_field(memory, "valid_from")),
        "valid_to": _safe(_field(memory, "valid_to")),
    }
    return EvidenceRef(
        id=identifier,
        kind=EvidenceKind.MEMORY,
        memory_id=identifier,
        source_id=source_ids[0] if source_ids else None,
        message_id=_field(memory, "source_message_id"),
        excerpt=_memory_text(memory) if include_excerpt else None,
        metadata=metadata,
    )


def _evidence_from_core(value: Any) -> EvidenceRef | None:
    identifier = _field(value, "evidence_id") or _field(value, "memory_id") or _field(value, "id")
    if identifier is None and _field(value, "memory") is not None:
        identifier = _memory_id(_field(value, "memory"))
    if identifier is None:
        return None
    memory = _field(value, "memory")
    source_ids = _source_values(value)
    if not source_ids and memory is not None:
        source_ids = _source_values(memory)
    metadata = _field(value, "metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    evidence_metadata = {
        "memory_type": _safe(_field(value, "memory_type") or _field(memory, "memory_type")),
        "source_type": _safe(_field(value, "source_type") or _field(memory, "source_type")),
        "structured_data": _safe(_field(value, "structured_data") or _field(memory, "structured_data")),
        "temporal_metadata": _safe(_field(value, "temporal_metadata")),
        "rank": _safe(_field(value, "rank")),
    }
    evidence_metadata.update(_safe(dict(metadata)))
    return EvidenceRef(
        id=str(identifier),
        kind=EvidenceKind.MEMORY,
        memory_id=str(_field(value, "memory_id") or _memory_id(memory) if memory is not None else identifier),
        source_id=source_ids[0] if source_ids else None,
        message_id=_field(value, "source_message_id") or (source_ids[1] if len(source_ids) > 1 else None),
        excerpt=str(
            _field(value, "content") or _memory_text(memory) if memory is not None else _field(value, "content") or ""
        ),
        metadata=evidence_metadata,
    )


def _core_kind(value: Any) -> ContextBlockKind:
    name = str(_enum_value(value) or "").casefold()
    return {
        "profile": ContextBlockKind.IDENTITY,
        "identity": ContextBlockKind.IDENTITY,
        "preference": ContextBlockKind.PREFERENCE,
        "rule": ContextBlockKind.RULE,
        "procedural": ContextBlockKind.RULE,
        "project": ContextBlockKind.PROJECT,
        "goal": ContextBlockKind.GOAL,
        "event": ContextBlockKind.EVENT,
        "episodic": ContextBlockKind.EVENT,
        "conversation": ContextBlockKind.CONVERSATION,
        "graph": ContextBlockKind.GRAPH,
    }.get(name, ContextBlockKind.FACT)


def _token_count(value: str) -> int:
    return len(value.split()) if value else 0


def _call_with_supported_kwargs(method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        return method(*args, **kwargs)
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return method(*args, **kwargs)
    accepted = {name: value for name, value in kwargs.items() if name in parameters}
    return method(*args, **accepted)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class MemoryKernelAdapter:
    def __init__(
        self,
        session_factory: SessionFactory | None = None,
        *,
        orchestrator: FastMemoryOrchestrator | None = None,
        pipeline: FastMemoryOrchestrator | None = None,
        retrieval_engine: RetrievalEngine | None = None,
        retrieval_engine_factory: RetrievalEngineFactory | None = None,
        context_builder: ContextBuilder | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        if session_factory is None:
            from contexta.db import AsyncSessionFactory

            session_factory = AsyncSessionFactory
        self._session_factory = session_factory
        self._orchestrator = orchestrator if orchestrator is not None else pipeline
        self._retrieval_engine = retrieval_engine
        self._retrieval_engine_factory = retrieval_engine_factory
        self._context_builder = context_builder if context_builder is not None else ContextBuilder()
        self._embedding_service = embedding_service
        self._operations: dict[tuple[str, str, str], OperationResult] = {}
        self._idempotency: dict[tuple[str, str, str], tuple[str, OperationResult]] = {}

    @property
    def canonical_write_authority(self) -> Literal["contexta"]:
        return CANONICAL_WRITE_AUTHORITY

    @property
    def write_authority(self) -> Literal["contexta"]:
        return CANONICAL_WRITE_AUTHORITY

    @asynccontextmanager
    async def _transaction(self, *, write: bool = True) -> AsyncIterator[AsyncSession]:
        candidate = self._session_factory()
        candidate = await _maybe_await(candidate)
        if hasattr(candidate, "__aenter__") and hasattr(candidate, "__aexit__"):
            async with candidate as session:
                try:
                    yield session
                    if write:
                        await self._commit(session)
                except BaseException:
                    await self._rollback(session)
                    raise
            return
        session = candidate
        try:
            yield session
            if write:
                await self._commit(session)
        except BaseException:
            await self._rollback(session)
            raise
        finally:
            close = getattr(session, "close", None)
            if callable(close):
                with suppress(Exception):
                    await _maybe_await(close())

    @staticmethod
    async def _commit(session: Any) -> None:
        commit = getattr(session, "commit", None)
        if callable(commit):
            await _maybe_await(commit())

    @staticmethod
    async def _rollback(session: Any) -> None:
        rollback = getattr(session, "rollback", None)
        if callable(rollback):
            with suppress(Exception):
                await _maybe_await(rollback())

    def _ids(self, scope: Scope) -> tuple[UUID, UUID]:
        return (
            _uuid(scope.tenant_id, "scope.tenant_id"),
            _uuid(scope.account_id or scope.user_id, "scope.account_id"),
        )

    def _session_id(self, scope: Scope, metadata: Mapping[str, Any] | None = None) -> UUID:
        value = scope.session_id
        if value is None and metadata is not None:
            value = metadata.get("session_id")
        if value is None:
            value = scope.metadata.get("session_id")
        return _uuid(value, "scope.session_id") if value is not None else uuid4()

    def _repositories(
        self,
        session: AsyncSession,
        scope: Scope,
    ) -> tuple[MemoryRepository, EntityRepository, EntityEdgeRepository, MemoryEntityLinkRepository]:
        tenant_id, _ = self._ids(scope)
        return (
            MemoryRepository(session, tenant_id=tenant_id),
            EntityRepository(session, tenant_id=tenant_id),
            EntityEdgeRepository(session, tenant_id=tenant_id),
            MemoryEntityLinkRepository(session, tenant_id=tenant_id),
        )

    def _scope_matches_memory(self, memory: Any, scope: Scope) -> bool:
        organization_id, user_id = self._ids(scope)
        if _field(memory, "organization_id") != organization_id:
            return False
        if _field(memory, "user_id") != user_id:
            return False
        for name in ("memory_user_id", "agent_id", "project_id", "session_id"):
            requested = getattr(scope, name, None)
            actual = _field(memory, name)
            if requested is not None and str(actual) != str(requested):
                return False
        return True

    def _make_retrieval_engine(
        self,
        memory_repository: MemoryRepository,
        entity_repository: EntityRepository,
        edge_repository: EntityEdgeRepository,
        link_repository: MemoryEntityLinkRepository,
    ) -> RetrievalEngine:
        if self._retrieval_engine is not None:
            return self._retrieval_engine
        if self._retrieval_engine_factory is not None:
            factory = self._retrieval_engine_factory
            try:
                candidate = factory(
                    memory_repository=memory_repository,
                    entity_repository=entity_repository,
                    edge_repository=edge_repository,
                    link_repository=link_repository,
                )
            except TypeError:
                candidate = factory(memory_repository, link_repository, edge_repository, entity_repository)
            return candidate
        return RetrievalEngine(
            memory_repository=memory_repository,
            link_repository=link_repository,
            edge_repository=edge_repository,
            entity_repository=entity_repository,
        )

    async def _get_orchestrator(self) -> FastMemoryOrchestrator:
        if self._orchestrator is None:
            from contexta.config.settings import get_settings
            from contexta.core.cortex import ContextaCortex
            from contexta.core.extraction.worker import ExtractionWorker
            from contexta.services.llm import LLMService

            settings = get_settings()
            cortex_settings = settings.model_copy(update={"feature_cortex": False})
            self._orchestrator = FastMemoryOrchestrator(
                cortex=ContextaCortex(settings=cortex_settings),
                extraction_worker=ExtractionWorker(llm_service=LLMService(settings=settings)),
            )
        return self._orchestrator

    async def _get_embedding_service(self) -> EmbeddingService | None:
        if self._embedding_service is None:
            with suppress(Exception):
                self._embedding_service = EmbeddingService()
        return self._embedding_service

    async def _query_embedding(self, query: str) -> list[float] | None:
        service = await self._get_embedding_service()
        if service is None:
            return None
        with suppress(Exception):
            value = service.embed_text(query)
            value = await _maybe_await(value)
            if value is not None:
                return list(value)
        return None

    async def _retrieve(
        self,
        session: AsyncSession,
        scope: Scope,
        query: str,
        *,
        limit: int,
        graph_depth: int,
        memory_types: Sequence[str] = (),
        tags: Sequence[str] = (),
        include_cold: bool = True,
        include_archived: bool = False,
        as_of: datetime | None = None,
        temporal_mode: str = "auto",
    ) -> list[RetrievalResult]:
        organization_id, user_id = self._ids(scope)
        selected_types: list[MemoryType] | None = None
        if memory_types:
            selected_types = []
            for value in memory_types:
                try:
                    selected_types.append(value if isinstance(value, MemoryType) else MemoryType(value))
                except ValueError as exc:
                    raise ValueError(f"Unsupported memory type: {value}") from exc
        memory_repository, entity_repository, edge_repository, link_repository = self._repositories(session, scope)
        engine = self._make_retrieval_engine(
            memory_repository,
            entity_repository,
            edge_repository,
            link_repository,
        )
        engine = await _maybe_await(engine)
        retrieval_query = RetrievalQuery(
            user_id=user_id,
            memory_user_id=_optional_uuid(scope.memory_user_id, "scope.memory_user_id"),
            agent_id=_optional_uuid(scope.agent_id, "scope.agent_id"),
            project_id=_optional_uuid(scope.project_id, "scope.project_id"),
            session_id=_optional_uuid(scope.session_id, "scope.session_id"),
            organization_id=organization_id,
            query_text=query,
            limit=limit,
            graph_depth=graph_depth,
            memory_types=selected_types,
            tags=list(tags) if tags else None,
            include_cold=include_cold,
            include_archived=include_archived,
            as_of=as_of,
            temporal_mode=temporal_mode,
        )
        embedding = await self._query_embedding(query)
        result = _call_with_supported_kwargs(
            engine.retrieve,
            retrieval_query,
            query_embedding=embedding,
            now=as_of or datetime.now(UTC),
        )
        result = await _maybe_await(result)
        return list(result or [])

    @staticmethod
    def _redact(value: Any) -> Any:
        from contexta.core.extraction.sensitive_filter import primary_scan

        if isinstance(value, str):
            return primary_scan(value).redacted_content
        if isinstance(value, Mapping):
            return {str(key): MemoryKernelAdapter._redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [MemoryKernelAdapter._redact(item) for item in value]
        if isinstance(value, tuple):
            return tuple(MemoryKernelAdapter._redact(item) for item in value)
        return value

    def _observation_payload(self, request: ObserveRequest, operation_id: str) -> ObservationPayload:
        messages: list[dict[str, Any]] = []
        if request.content is not None:
            messages.append({"role": "user", "content": self._redact(request.content)})
        for message in request.messages:
            item: dict[str, Any] = {
                "role": message.role,
                "content": self._redact(message.content),
            }
            if message.message_id is not None:
                item["message_id"] = message.message_id
            if message.occurred_at is not None:
                item["occurred_at"] = message.occurred_at
            if message.metadata:
                item["metadata"] = self._redact(dict(message.metadata))
            messages.append(item)
        for index, event in enumerate(request.events):
            event_id = event.event_id or f"{operation_id}:event:{index}"
            item = {
                "role": str(event.metadata.get("role", "user")),
                "content": self._redact(event.content),
                "event_id": event_id,
                "event_index": index,
            }
            if event.source_id is not None:
                item["source_id"] = event.source_id
            if event.occurred_at is not None:
                item["occurred_at"] = event.occurred_at
            if event.observed_at is not None:
                item["observed_at"] = event.observed_at
            if event.metadata:
                item["metadata"] = self._redact(dict(event.metadata))
            messages.append(item)
        metadata = self._redact({**dict(request.scope.metadata), **dict(request.metadata)})
        metadata.setdefault("contract_operation_id", operation_id)
        for name in ("agent_id", "project_id", "session_id"):
            value = getattr(request.scope, name, None)
            if value is not None:
                metadata.setdefault(name, value)
        tenant_id, user_id = self._ids(request.scope)
        source_id = request.source_id or metadata.get("source_id")
        message_id = metadata.get("message_id")
        if message_id is None and request.messages:
            message_id = request.messages[0].message_id
        payload_metadata = dict(metadata)
        for key in (
            "event_at",
            "event_start",
            "event_end",
            "temporal_precision",
            "temporal_basis",
            "source_span",
            "source_message_id",
            "original_text",
            "normalized_text",
        ):
            if key in payload_metadata:
                payload_metadata[key] = payload_metadata[key]
        return ObservationPayload(
            user_id=user_id,
            memory_user_id=_optional_uuid(request.scope.memory_user_id or request.scope.user_id, "scope.memory_user_id"),
            agent_id=_optional_uuid(request.scope.agent_id, "scope.agent_id"),
            project_id=_optional_uuid(request.scope.project_id, "scope.project_id"),
            organization_id=tenant_id,
            session_id=self._session_id(request.scope, request.metadata),
            messages=messages,
            occurred_at=request.occurred_at,
            observed_at=request.observed_at,
            event_at=payload_metadata.get("event_at"),
            event_start=payload_metadata.get("event_start"),
            event_end=payload_metadata.get("event_end"),
            temporal_precision=payload_metadata.get("temporal_precision"),
            temporal_basis=payload_metadata.get("temporal_basis"),
            source_id=source_id,
            message_id=message_id,
            source_message_id=payload_metadata.get("source_message_id"),
            timezone=request.timezone or payload_metadata.get("timezone"),
            original_text=payload_metadata.get("original_text"),
            normalized_text=payload_metadata.get("normalized_text"),
            source_span=payload_metadata.get("source_span"),
            metadata=payload_metadata,
            policy=request.policy,
        )

    @staticmethod
    def _event_ids(request: ObserveRequest, operation_id: str) -> list[str]:
        values = [event.event_id or f"{operation_id}:event:{index}" for index, event in enumerate(request.events)]
        values.extend(message.message_id for message in request.messages if message.message_id)
        if request.content is not None and not values:
            values.append(f"{operation_id}:content")
        return list(dict.fromkeys(values))

    @staticmethod
    def _orchestration_ids(value: Any) -> list[str]:
        values: list[Any] = []
        for name in ("embedding_memory_ids",):
            values.extend(getattr(value, name, None) or [])
        for detail in getattr(value, "details", None) or []:
            if not isinstance(detail, Mapping):
                continue
            if detail.get("action") in {"store", "merge", "merge_in_batch"}:
                values.extend(detail.get(name) for name in ("memory_id", "existing_id") if detail.get(name) is not None)
        return list(dict.fromkeys(str(item) for item in values if item is not None and str(item)))

    async def _persist_embeddings(
        self,
        session: AsyncSession,
        scope: Scope,
        memory_ids: Sequence[str],
    ) -> dict[str, bool]:
        if not memory_ids:
            return {}
        service = await self._get_embedding_service()
        generate = getattr(service, "generate_and_store", None) if service is not None else None
        if not callable(generate):
            return {}
        memory_repository, _, _, _ = self._repositories(session, scope)
        statuses: dict[str, bool] = {}
        for identifier in memory_ids:
            parsed = _optional_uuid(identifier)
            if parsed is None:
                continue
            with suppress(Exception):
                memory = await memory_repository.get_by_id(parsed)
                if memory is None:
                    continue
                value = _call_with_supported_kwargs(
                    generate,
                    memory,
                    memory_repository,
                    enqueue_on_failure=False,
                )
                statuses[identifier] = bool(await _maybe_await(value))
        return statuses

    @staticmethod
    def _operation_error(kind: str, exc: Exception) -> OperationError:
        # The message and traceback are what make a kernel failure diagnosable; a
        # bare code like "recall_failed" forces a blind reproduction.
        logger.warning(
            "kernel operation failed: kind=%s exception_type=%s message=%s",
            kind,
            type(exc).__name__,
            exc,
        )
        return OperationError(
            code=f"{kind}_failed",
            message=f"{kind} failed: {type(exc).__name__}: {exc}"[:500],
            retryable=isinstance(exc, (OSError, RuntimeError, TimeoutError)),
            details={
                "exception_type": type(exc).__name__,
                "exception_message": str(exc)[:500],
            },
        )

    def _remember(self, result: OperationResult) -> None:
        key = (result.scope.tenant_id, result.scope.user_id, result.operation_id)
        self._operations[key] = result

    def _remember_idempotent(
        self,
        result: OperationResult,
        fingerprint: str,
    ) -> None:
        if result.idempotency_key is None:
            return
        key = (result.scope.tenant_id, result.scope.user_id, result.idempotency_key)
        self._idempotency[key] = (fingerprint, result)

    def _operation_id(self, request: Any) -> str:
        return request.request_id or uuid4().hex

    async def observe(self, request: ObserveRequest) -> ObserveResult:
        operation_id = self._operation_id(request)
        fingerprint = hashlib.sha256(
            json.dumps(request.model_dump(mode="json"), sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        idempotency_key = (request.scope.tenant_id, request.scope.user_id, request.idempotency_key)
        previous = self._idempotency.get(idempotency_key)
        if previous is not None:
            previous_fingerprint, previous_result = previous
            if previous_fingerprint == fingerprint and isinstance(previous_result, ObserveResult):
                return previous_result
            result = ObserveResult(
                operation_id=operation_id,
                kind=OperationKind.OBSERVE,
                status=OperationStatus.CONFLICT,
                scope=request.scope,
                idempotency_key=request.idempotency_key,
                result={"accepted": False},
                error=OperationError(
                    code="idempotency_conflict",
                    message="The idempotency key was already used with a different observation.",
                ),
                metadata={"canonical_write_authority": CANONICAL_WRITE_AUTHORITY},
            )
            self._remember(result)
            return result
        try:
            async with self._transaction(write=True) as session:
                payload = self._observation_payload(request, operation_id)
                orchestrator = await self._get_orchestrator()
                orchestrated = await _maybe_await(orchestrator.orchestrate(payload, session))
                memory_ids = self._orchestration_ids(orchestrated)
                embedding_status = await self._persist_embeddings(session, request.scope, memory_ids)
                evidence = [
                    EvidenceRef(
                        id=identifier,
                        kind=EvidenceKind.MEMORY,
                        memory_id=identifier,
                        metadata={"source": "observe"},
                    )
                    for identifier in memory_ids
                ]
                result_payload = {
                    "extracted_count": getattr(orchestrated, "extracted_count", 0),
                    "stored_count": getattr(orchestrated, "stored_count", 0),
                    "merged_count": getattr(orchestrated, "merged_count", 0),
                    "discarded_count": getattr(orchestrated, "discarded_count", 0),
                    "details": getattr(orchestrated, "details", []),
                    "timings": getattr(orchestrated, "timings", None),
                    "completed": True,
                }
                result = ObserveResult(
                    operation_id=operation_id,
                    kind=OperationKind.OBSERVE,
                    status=OperationStatus.ACCEPTED,
                    scope=request.scope,
                    idempotency_key=request.idempotency_key,
                    result=_safe(result_payload),
                    evidence=evidence,
                    observation_id=operation_id,
                    accepted_event_ids=self._event_ids(request, operation_id),
                    memory_ids=memory_ids,
                    metadata={
                        "canonical_write_authority": CANONICAL_WRITE_AUTHORITY,
                        "pipeline": "FastMemoryOrchestrator",
                        "embedding_status": embedding_status,
                    },
                )
        except (
            AttributeError,
            KeyError,
            OSError,
            PydanticValidationError,
            RuntimeError,
            SQLAlchemyError,
            TypeError,
            ValueError,
            contextaError,
        ) as exc:
            result = ObserveResult(
                operation_id=operation_id,
                kind=OperationKind.OBSERVE,
                status=OperationStatus.FAILED,
                scope=request.scope,
                idempotency_key=request.idempotency_key,
                result={"accepted": False},
                error=self._operation_error("observe", exc),
                metadata={"canonical_write_authority": CANONICAL_WRITE_AUTHORITY},
            )
        self._remember(result)
        self._remember_idempotent(result, fingerprint)
        return result

    def _hit(self, value: RetrievalResult | Any, *, include_evidence: bool) -> MemoryHit:
        memory = _field(value, "memory", value)
        scores = {
            "dense": float(_field(value, "semantic_score", 0.0) or 0.0),
            "lexical": float(_field(value, "keyword_score", 0.0) or 0.0),
            "graph": float(_field(value, "graph_score", 0.0) or 0.0),
            "importance": float(_field(value, "importance_score", 0.0) or 0.0),
            "recency": float(_field(value, "recency_score", 0.0) or 0.0),
            "total": float(_field(value, "score", 0.0) or 0.0),
        }
        evidence = [_memory_evidence(memory)] if include_evidence else []
        return MemoryHit(
            memory_id=_memory_id(memory),
            title=_field(memory, "title"),
            content=_memory_text(memory),
            memory_type=str(_enum_value(_field(memory, "memory_type", "custom")) or "custom"),
            score=scores["total"],
            scores=scores,
            valid_from=_field(memory, "valid_from"),
            valid_to=_field(memory, "valid_to"),
            evidence=evidence,
            metadata={
                "importance": _safe(_field(memory, "importance", 0.0)),
                "confidence": _safe(_field(memory, "confidence", 0.0)),
                "source_ids": _source_values(memory),
                "memory_state": _safe(_field(memory, "memory_state")),
            },
        )

    async def recall(self, request: RecallRequest) -> RecallResult:
        operation_id = self._operation_id(request)
        try:
            async with self._transaction(write=True) as session:
                values = await self._retrieve(
                    session,
                    request.scope,
                    request.query,
                    limit=request.limit,
                    graph_depth=request.graph_depth,
                    memory_types=request.memory_types,
                    tags=request.tags,
                    include_cold=request.include_cold,
                    include_archived=request.include_archived,
                    as_of=request.as_of,
                    temporal_mode=request.temporal_mode,
                )
                hits = [self._hit(value, include_evidence=request.include_evidence) for value in values]
                evidence: list[EvidenceRef] = []
                seen: set[str] = set()
                for hit in hits:
                    for reference in hit.evidence:
                        if reference.id not in seen:
                            seen.add(reference.id)
                            evidence.append(reference)
                result = RecallResult(
                    operation_id=operation_id,
                    kind=OperationKind.RECALL,
                    status=OperationStatus.COMPLETED,
                    scope=request.scope,
                    result={
                        "results": [hit.model_dump(mode="json", by_alias=True) for hit in hits],
                        "total": len(hits),
                    },
                    evidence=evidence,
                    query=request.query,
                    results=hits,
                    total=len(hits),
                    metadata={"retrieval_engine": "RetrievalEngine"},
                )
        except (
            AttributeError,
            KeyError,
            OSError,
            PydanticValidationError,
            RuntimeError,
            SQLAlchemyError,
            TypeError,
            ValueError,
            contextaError,
        ) as exc:
            result = RecallResult(
                operation_id=operation_id,
                kind=OperationKind.RECALL,
                status=OperationStatus.FAILED,
                scope=request.scope,
                result={"results": [], "total": 0},
                error=self._operation_error("recall", exc),
                query=request.query,
                metadata={"retrieval_engine": "RetrievalEngine"},
            )
        self._remember(result)
        return result

    def _core_context_request(self, request: BuildContextRequest) -> ContextRequest:
        organization_id, user_id = self._ids(request.scope)
        config = ContextConfig(
            num_recent_messages=max(1, len(request.messages) or 10),
            num_relevant_memories=request.max_memories,
            graph_depth=request.graph_depth,
            include_user_model=request.include_user_model,
            token_budget=request.token_budget,
        )
        return ContextRequest(
            user_id=user_id,
            memory_user_id=_optional_uuid(request.scope.memory_user_id, "scope.memory_user_id"),
            agent_id=_optional_uuid(request.scope.agent_id, "scope.agent_id"),
            project_id=_optional_uuid(request.scope.project_id, "scope.project_id"),
            organization_id=organization_id,
            session_id=self._session_id(request.scope, request.metadata),
            config=config,
        )

    async def _build_core_context(
        self,
        request: BuildContextRequest,
        core_request: ContextRequest,
        memories: Sequence[Any],
    ) -> Any:
        builder = self._context_builder
        newest = None
        timestamps = [_field(_field(memory, "memory", memory), "created_at") for memory in memories]
        timestamps = [value for value in timestamps if isinstance(value, datetime)]
        if timestamps:
            newest = max(timestamps).isoformat()
        required = request.metadata.get("required_evidence_ids", [])
        if not isinstance(required, (list, tuple, set)):
            required = []
        build_package = getattr(builder, "build_package", None)
        if callable(build_package):
            value = _call_with_supported_kwargs(
                build_package,
                core_request,
                memories,
                query=request.focus or "",
                required_evidence_ids=[str(item) for item in required],
                newest_memory_timestamp=newest,
                token_budget=request.token_budget,
            )
            value = await _maybe_await(value)
            if value is not None and not hasattr(value, "evidence") and hasattr(value, "ordered_items"):
                return CoreContextPackageBuilder().build_from_context(
                    request.focus or "",
                    value,
                    required_evidence_ids=[str(item) for item in required],
                    token_budget=request.token_budget,
                )
            return value
        built = _call_with_supported_kwargs(
            builder.build,
            core_request,
            memories,
            newest_memory_timestamp=newest,
            required_evidence_ids=[str(item) for item in required],
        )
        built = await _maybe_await(built)
        package_builder = CoreContextPackageBuilder()
        return package_builder.build_from_context(
            request.focus or "",
            built,
            required_evidence_ids=[str(item) for item in required],
            token_budget=request.token_budget,
        )

    def _contract_context(
        self,
        request: BuildContextRequest,
        internal: Any,
        operation_id: str,
    ) -> ContextPackage:
        blocks: list[ContextBlock] = []
        references: list[EvidenceRef] = []
        if isinstance(internal, ContextPackage):
            blocks = list(internal.blocks)
            references = list(internal.evidence)
            metadata = dict(internal.metadata)
        else:
            values = _field(internal, "evidence")
            if not isinstance(values, list):
                values = []
            for value in values:
                reference = _evidence_from_core(value)
                if reference is not None:
                    references.append(reference)
                    content = str(_field(value, "content", "") or "")
                    title = _field(value, "title")
                    if title and str(title) not in content:
                        content = f"{title}\n{content}"
                    blocks.append(
                        ContextBlock(
                            block_id=f"memory:{reference.id}",
                            kind=_core_kind(_field(value, "memory_type")),
                            content=content,
                            evidence=[reference],
                            version=0,
                            token_count=_token_count(content),
                            metadata={
                                "memory_id": reference.id,
                                "memory_type": _safe(_field(value, "memory_type")),
                                "rank": _safe(_field(value, "rank")),
                            },
                        )
                    )
            metadata = dict(_field(internal, "metadata", {}) or {})
        if not request.include_user_model:
            blocks = [
                block for block in blocks if block.kind not in {ContextBlockKind.IDENTITY, ContextBlockKind.PREFERENCE}
            ]
        if request.include_recent_messages and request.messages:
            content = "\n".join(f"{message.role}: {message.content}" for message in request.messages)
            blocks.append(
                ContextBlock(
                    block_id=f"conversation:{operation_id}",
                    kind=ContextBlockKind.CONVERSATION,
                    content=content,
                    version=0,
                    token_count=_token_count(content),
                    metadata={"message_count": len(request.messages)},
                )
            )
        if not request.include_evidence:
            references = []
            blocks = [block.model_copy(update={"evidence": []}) for block in blocks]
        if request.max_memories < len(blocks):
            non_conversation = [block for block in blocks if block.kind != ContextBlockKind.CONVERSATION]
            conversation = [block for block in blocks if block.kind == ContextBlockKind.CONVERSATION]
            blocks = [*non_conversation[: request.max_memories], *conversation]
        if request.token_budget is not None:
            remaining = request.token_budget
            bounded: list[ContextBlock] = []
            for block in blocks:
                count = block.token_count or _token_count(block.content)
                if count <= remaining:
                    bounded.append(block)
                    remaining -= count
                    continue
                if remaining <= 0:
                    break
                words = block.content.split()
                content = " ".join(words[:remaining])
                bounded.append(
                    block.model_copy(
                        update={
                            "content": content,
                            "token_count": remaining,
                        }
                    )
                )
                remaining = 0
            blocks = bounded
        unique_references: list[EvidenceRef] = []
        seen: set[str] = set()
        for reference in [*references, *(item for block in blocks for item in block.evidence)]:
            if reference.id not in seen:
                seen.add(reference.id)
                unique_references.append(reference)
        metadata = {
            "answerable": _safe(_field(internal, "answerable")),
            "answerability": _safe(_field(internal, "answerability")),
            "answerability_score": _safe(_field(internal, "answerability_score")),
            "evidence_ids": [reference.id for reference in unique_references],
            "source_ids": list(
                dict.fromkeys(
                    source
                    for reference in unique_references
                    for source in ([reference.source_id] if reference.source_id else [])
                )
            ),
            "core_query": _safe(_field(internal, "query", request.focus or "")),
            "core_context": metadata,
            "canonical_write_authority": CANONICAL_WRITE_AUTHORITY,
        }
        package = ContextPackage(
            package_id=uuid4().hex,
            scope=request.scope,
            operation_id=operation_id,
            blocks=blocks,
            evidence=unique_references,
            text=None,
            token_budget=request.token_budget,
            token_count=0,
            metadata=_safe(metadata),
        )
        text = package.to_prompt(request.format)
        return package.model_copy(
            update={
                "text": text,
                "token_count": _token_count(text),
            }
        )

    async def build_context(self, request: BuildContextRequest) -> ContextPackage:
        operation_id = self._operation_id(request)
        try:
            async with self._transaction(write=True) as session:
                memory_repository, _, _, _ = self._repositories(session, request.scope)
                _, user_id = self._ids(request.scope)
                if request.focus:
                    memories = await self._retrieve(
                        session,
                        request.scope,
                        request.focus,
                        limit=request.max_memories,
                        graph_depth=request.graph_depth,
                    )
                else:
                    memories = [
                        memory
                        for memory in await memory_repository.get_current_truths(
                            user_id,
                            limit=max(100, request.max_memories * 5),
                            memory_user_id=_optional_uuid(request.scope.memory_user_id, "scope.memory_user_id"),
                            agent_id=_optional_uuid(request.scope.agent_id, "scope.agent_id"),
                            project_id=_optional_uuid(request.scope.project_id, "scope.project_id"),
                            session_id=_optional_uuid(request.scope.session_id, "scope.session_id"),
                        )
                        if self._scope_matches_memory(memory, request.scope)
                    ]
                core_request = self._core_context_request(request)
                internal = await self._build_core_context(request, core_request, memories)
                package = self._contract_context(request, internal, operation_id)
        except (
            AttributeError,
            KeyError,
            OSError,
            PydanticValidationError,
            RuntimeError,
            SQLAlchemyError,
            TypeError,
            ValueError,
            contextaError,
        ) as exc:
            package = ContextPackage(
                package_id=uuid4().hex,
                scope=request.scope,
                operation_id=operation_id,
                blocks=[],
                evidence=[],
                text="",
                token_budget=request.token_budget,
                token_count=0,
                metadata={
                    "error": self._operation_error("build_context", exc).model_dump(mode="json"),
                    "canonical_write_authority": CANONICAL_WRITE_AUTHORITY,
                },
            )
        self._remember(
            OperationResult(
                operation_id=operation_id,
                kind=OperationKind.BUILD_CONTEXT,
                status=(OperationStatus.FAILED if "error" in package.metadata else OperationStatus.COMPLETED),
                scope=request.scope,
                result=package.serialize(),
            )
        )
        return package

    def _memory_snapshot(self, memory: MemoryRecord) -> dict[str, Any]:
        return {
            "memory_id": _memory_id(memory),
            "title": _field(memory, "title"),
            "content": _memory_text(memory),
            "memory_type": _safe(_field(memory, "memory_type")),
            "importance": _safe(_field(memory, "importance", 0.0)),
            "confidence": _safe(_field(memory, "confidence", 0.0)),
            "source_ids": _source_values(memory),
            "valid_from": _safe(_field(memory, "valid_from")),
            "valid_to": _safe(_field(memory, "valid_to")),
            "structured_data": _safe(_field(memory, "structured_data")),
        }

    async def explain(self, request: ExplainRequest) -> ExplanationResult:
        operation_id = self._operation_id(request)
        try:
            memory_id = _uuid(request.memory_id, "memory_id")
            async with self._transaction(write=True) as session:
                memory_repository, _, _, _ = self._repositories(session, request.scope)
                _, _ = self._ids(request.scope)
                memory = await memory_repository.get_by_id(memory_id)
                if memory is None or not self._scope_matches_memory(memory, request.scope):
                    result = ExplanationResult(
                        operation_id=operation_id,
                        kind=OperationKind.EXPLAIN,
                        status=OperationStatus.NOT_FOUND,
                        scope=request.scope,
                        result={"memory_id": request.memory_id},
                        memory_id=request.memory_id,
                        summary="",
                        error=OperationError(
                            code="memory_not_found",
                            message="The memory was not found in the requested scope.",
                        ),
                    )
                else:
                    touch = getattr(memory_repository, "touch_accessed", None)
                    if callable(touch):
                        await _maybe_await(touch(memory.id, datetime.now(UTC).replace(tzinfo=None)))
                    content = _memory_text(memory)
                    title = str(_field(memory, "title", "") or "")
                    evidence = [_memory_evidence(memory)] if request.include_evidence else []
                    rationale = [
                        f"memory_type={_safe(_field(memory, 'memory_type', 'custom'))}",
                        f"importance={_safe(_field(memory, 'importance', 0.0))}",
                        f"confidence={_safe(_field(memory, 'confidence', 0.0))}",
                    ]
                    if _field(memory, "valid_from") is not None:
                        rationale.append(f"valid_from={_safe(_field(memory, 'valid_from'))}")
                    if _field(memory, "valid_to") is not None:
                        rationale.append(f"superseded_at={_safe(_field(memory, 'valid_to'))}")
                    if request.question:
                        rationale.append(f"question={request.question}")
                    result = ExplanationResult(
                        operation_id=operation_id,
                        kind=OperationKind.EXPLAIN,
                        status=OperationStatus.COMPLETED,
                        scope=request.scope,
                        result=self._memory_snapshot(memory),
                        supporting_evidence=evidence,
                        memory_id=request.memory_id,
                        summary=(f"{title}: {content}" if title else content)[:2000],
                        rationale=rationale,
                        metadata={"deterministic": True},
                    )
        except (
            AttributeError,
            KeyError,
            OSError,
            PydanticValidationError,
            RuntimeError,
            SQLAlchemyError,
            TypeError,
            ValueError,
            contextaError,
        ) as exc:
            result = ExplanationResult(
                operation_id=operation_id,
                kind=OperationKind.EXPLAIN,
                status=OperationStatus.FAILED,
                scope=request.scope,
                result={"memory_id": request.memory_id},
                memory_id=request.memory_id,
                summary="",
                error=self._operation_error("explain", exc),
            )
        self._remember(result)
        return result

    async def correct(self, request: CorrectRequest) -> CorrectionResult:
        result = CorrectionResult(
            operation_id=self._operation_id(request),
            kind=OperationKind.CORRECT,
            status=OperationStatus.QUEUED,
            scope=request.scope,
            idempotency_key=request.idempotency_key,
            result={
                "supported": False,
                "status": "queued",
                "memory_id": request.memory_id,
                "message": "Corrections require a reviewed canonical truth-maintenance workflow.",
            },
            evidence=request.evidence,
            memory_id=request.memory_id,
            status_detail="Queued without mutation; canonical writes remain owned by Contexta.",
            metadata={"canonical_write_authority": CANONICAL_WRITE_AUTHORITY},
        )
        self._remember(result)
        return result

    async def propose_block_update(
        self,
        request: ProposeBlockUpdateRequest,
    ) -> BlockUpdateProposal:
        result = BlockUpdateProposal(
            operation_id=self._operation_id(request),
            kind=OperationKind.PROPOSE_BLOCK_UPDATE,
            status=OperationStatus.PROPOSED,
            scope=request.scope,
            idempotency_key=request.idempotency_key,
            result={
                "supported": False,
                "status": "proposed",
                "message": "Block updates require a reviewed proposal workflow.",
            },
            evidence=request.evidence,
            proposal_id=uuid4().hex,
            block_id=request.block_id,
            operation=request.operation,
            content=request.content,
            expected_version=request.expected_version,
            applied=False,
            requires_review=True,
            metadata={"canonical_write_authority": CANONICAL_WRITE_AUTHORITY},
        )
        self._remember(result)
        return result

    async def search_graph(self, request: SearchGraphRequest) -> GraphSearchResult:
        operation_id = self._operation_id(request)
        try:
            async with self._transaction(write=True) as session:
                memory_repository, entity_repository, edge_repository, link_repository = self._repositories(
                    session, request.scope
                )
                _, user_id = self._ids(request.scope)
                seeds: set[UUID] = set()
                for value in [request.root_entity_id, *request.entity_ids]:
                    parsed = _optional_uuid(value)
                    if parsed is not None:
                        seeds.add(parsed)
                names = []
                if request.query:
                    names = list(
                        dict.fromkeys(
                            word.casefold()
                            for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]+", request.query)
                            if len(word) > 2
                        )
                    )
                if names:
                    getter = getattr(entity_repository, "get_by_names", None)
                    if callable(getter):
                        entities = await _maybe_await(getter(user_id, names))
                    else:
                        entities = []
                        for name in names:
                            single = getattr(entity_repository, "get_by_name", None)
                            if callable(single):
                                entity = await _maybe_await(single(user_id, name))
                                if entity is not None:
                                    entities.append(entity)
                    for entity in entities or []:
                        if getattr(entity, "user_id", user_id) == user_id:
                            parsed = _optional_uuid(getattr(entity, "id", None))
                            if parsed is not None:
                                seeds.add(parsed)
                nodes: dict[str, GraphNode] = {}
                edges: dict[tuple[str, str, str], GraphEdge] = {}
                linked_ids: list[UUID] = []
                visited: set[UUID] = set()
                frontier = set(seeds)
                for depth in range(request.max_hops + 1):
                    next_frontier: set[UUID] = set()
                    for entity_id in frontier:
                        if entity_id in visited:
                            continue
                        visited.add(entity_id)
                        entity = await entity_repository.get_by_id(entity_id)
                        if entity is not None and getattr(entity, "user_id", user_id) == user_id:
                            identifier = str(entity.id)
                            if len(nodes) < request.limit:
                                nodes[identifier] = GraphNode(
                                    id=identifier,
                                    name=str(entity.name or identifier),
                                    entity_type=_safe(getattr(entity, "entity_type", None)),
                                    metadata={
                                        "summary": _safe(getattr(entity, "summary", None)),
                                        "status": _safe(getattr(entity, "status", None)),
                                    },
                                )
                        links = await link_repository.get_memories_for_entity(entity_id)
                        for link in links or []:
                            memory_id = _optional_uuid(getattr(link, "memory_id", None))
                            if memory_id is not None and memory_id not in linked_ids:
                                linked_ids.append(memory_id)
                        neighbors = await edge_repository.get_neighbors(entity_id)
                        for edge in neighbors or []:
                            source = _optional_uuid(getattr(edge, "source_entity_id", None))
                            target = _optional_uuid(getattr(edge, "target_entity_id", None))
                            if source is None or target is None:
                                continue
                            direction = request.direction.value
                            if direction == GraphDirection.OUTGOING.value and source != entity_id:
                                continue
                            if direction == GraphDirection.INCOMING.value and target != entity_id:
                                continue
                            relationship = str(getattr(edge, "relationship_type", "") or "")
                            if (
                                not relationship
                                or request.relationship_types
                                and relationship not in request.relationship_types
                            ):
                                continue
                            key = (str(source), str(target), relationship)
                            if len(edges) < request.limit:
                                edges[key] = GraphEdge(
                                    source=str(source),
                                    target=str(target),
                                    relationship_type=relationship,
                                )
                            if depth < request.max_hops:
                                next_frontier.add(source)
                                next_frontier.add(target)
                    frontier = next_frontier - visited
                memory_records = []
                if linked_ids:
                    getter = getattr(memory_repository, "get_many_by_ids", None)
                    if callable(getter):
                        memory_records = list(await _maybe_await(getter(linked_ids)) or [])
                    else:
                        for memory_id in linked_ids:
                            memory = await memory_repository.get_by_id(memory_id)
                            if memory is not None:
                                memory_records.append(memory)
                linked_memories: list[LinkedMemory] = []
                for memory in memory_records:
                    if not self._scope_matches_memory(memory, request.scope):
                        continue
                    if len(linked_memories) >= request.limit:
                        break
                    evidence = [_memory_evidence(memory)] if request.include_evidence else []
                    linked_memories.append(
                        LinkedMemory(
                            memory_id=_memory_id(memory),
                            title=_field(memory, "title"),
                            content=_memory_text(memory),
                            evidence=evidence,
                        )
                    )
                result = GraphSearchResult(
                    operation_id=operation_id,
                    kind=OperationKind.SEARCH_GRAPH,
                    status=OperationStatus.COMPLETED,
                    scope=request.scope,
                    result={
                        "nodes": [node.model_dump(mode="json") for node in nodes.values()],
                        "edges": [edge.model_dump(mode="json") for edge in edges.values()],
                        "linked_memories": [item.model_dump(mode="json") for item in linked_memories],
                    },
                    query=request.query,
                    nodes=list(nodes.values()),
                    edges=list(edges.values()),
                    linked_memories=linked_memories,
                    metadata={"tenant_scoped": True},
                )
        except (
            AttributeError,
            KeyError,
            OSError,
            PydanticValidationError,
            RuntimeError,
            SQLAlchemyError,
            TypeError,
            ValueError,
            contextaError,
        ) as exc:
            result = GraphSearchResult(
                operation_id=operation_id,
                kind=OperationKind.SEARCH_GRAPH,
                status=OperationStatus.FAILED,
                scope=request.scope,
                result={"nodes": [], "edges": [], "linked_memories": []},
                query=request.query,
                error=self._operation_error("search_graph", exc),
                metadata={"tenant_scoped": True},
            )
        self._remember(result)
        return result

    async def get_operation(self, request: GetOperationRequest) -> OperationResult | None:
        return self._operations.get((request.scope.tenant_id, request.scope.user_id, request.operation_id))

    @staticmethod
    def serialize_context_package(package: ContextPackage) -> dict[str, Any]:
        return serialize_context_package(package)

    @staticmethod
    def deserialize_context_package(
        payload: Mapping[str, Any] | str | bytes,
    ) -> ContextPackage:
        return deserialize_context_package(payload)


ContextaKernel = MemoryKernelAdapter
ContextaMemoryKernel = MemoryKernelAdapter
MemoryKernelService = MemoryKernelAdapter
Kernel = MemoryKernelAdapter

__all__ = [
    "ContextaKernel",
    "ContextaMemoryKernel",
    "Kernel",
    "MemoryKernelAdapter",
    "MemoryKernelService",
]

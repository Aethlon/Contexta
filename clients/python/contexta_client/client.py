from __future__ import annotations

import os
import warnings
from types import TracebackType
from typing import Any, Self
from uuid import UUID

from contexta_client._context_builder import Context
from contexta_client._http import HTTPClient, TLSConfig
from contexta_client._types import (
    BatchObserveResponse,
    DeleteResult,
    Explanation,
    FeedbackResult,
    Memory,
    MemoryFlag,
    MemoryListEntry,
    ObserveResponse,
    Policy,
    ReflectResult,
    Schema,
    ScoredMemory,
    Session,
    TimelineEvent,
)

__all__ = ["Contexta"]


class Contexta:
    """Synchronous Contexta SDK client.

    ``Contexta`` is safe to use as a context manager and ``close()`` may be called
    repeatedly:

    ::

        with Contexta(api_key="mk_live_...") as memory:
            memory.observe(user_id=user_id, messages=[{"role": "user", "content": "hi"}])
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.contexta.dev/v1",
        timeout: float = 30.0,
        max_retries: int = 3,
        telemetry: bool = True,
        enable_buffer: bool = True,
        buffer_path: str | None = None,
        organization_id: str | None = None,
        verify_tls: bool = True,
        ca_bundle: TLSConfig | None = None,
        ca_bundle_path: str | None = None,
    ) -> None:
        """Create a client.

        ``organization_id`` is required by routes that take an explicit tenant
        (``context``, ``create_session``); the server rejects a mismatch against
        the organization bound to the API key. ``verify_tls`` defaults to ``True``.
        Point ``ca_bundle_path`` at the local gateway's certificate authority to
        trust a self-signed deployment, or pass ``ca_bundle`` with PEM contents.
        Passing ``verify_tls=False`` is an explicit opt-in that disables
        verification entirely.
        """
        self.organization_id = organization_id
        self._http = HTTPClient(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            telemetry=telemetry,
            enable_buffer=enable_buffer,
            buffer_path=buffer_path,
            verify_tls=verify_tls,
            ca_bundle=ca_bundle,
            ca_bundle_path=ca_bundle_path,
        )

    @classmethod
    def from_env(cls) -> Contexta:
        """Build a client from ``CONTEXTA_*`` environment variables."""
        api_key = os.environ.get("CONTEXTA_API_KEY")
        if not api_key:
            raise ValueError("CONTEXTA_API_KEY environment variable is required")
        ca_bundle_path = os.environ.get("CONTEXTA_CA_BUNDLE")
        return cls(
            api_key=api_key,
            base_url=os.environ.get("CONTEXTA_API_URL", "https://api.contexta.dev/v1"),
            timeout=float(os.environ.get("CONTEXTA_TIMEOUT_MS", "30000")) / 1000.0,
            max_retries=int(os.environ.get("CONTEXTA_MAX_RETRIES", "3")),
            telemetry=os.environ.get("CONTEXTA_TELEMETRY", "true").lower() != "false",
            organization_id=os.environ.get("CONTEXTA_ORGANIZATION_ID"),
            verify_tls=os.environ.get("CONTEXTA_VERIFY_TLS", "true").lower() != "false",
            ca_bundle_path=ca_bundle_path,
        )

    def _require_organization_id(self, organization_id: str | None) -> str:
        resolved = organization_id or self.organization_id
        if not resolved:
            raise ValueError(
                "organization_id is required by this endpoint. Pass "
                "organization_id=... or set CONTEXTA_ORGANIZATION_ID / the "
                "organization_id constructor argument."
            )
        return str(UUID(str(resolved)))

    def observe(
        self,
        *,
        user_id: str,
        session_id: str | None = None,
        messages: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
        policy: str | None = None,
        idempotency_key: str | None = None,
        occurred_at: str | None = None,
        observed_at: str | None = None,
        source_id: str | None = None,
        message_id: str | None = None,
        timezone: str | None = None,
    ) -> ObserveResponse:
        body: dict[str, Any] = {
            "messages": messages,
        }
        if session_id:
            body["session_id"] = session_id
        if metadata:
            body["metadata"] = metadata
        if policy:
            body["policy"] = policy
        if occurred_at:
            body["occurred_at"] = occurred_at
        if observed_at:
            body["observed_at"] = observed_at
        if source_id:
            body["source_id"] = source_id
        if message_id:
            body["message_id"] = message_id
        if timezone:
            body["timezone"] = timezone
        headers = {"X-contexta-User-Id": user_id}
        data = self._http._request(
            method="POST",
            endpoint="/observations",
            body=body,
            idempotency_key=idempotency_key,
            headers=headers,
            is_write=True,
        )
        self._http.flush_buffer()
        return ObserveResponse(**data)

    def observe_batch(
        self,
        observations: list[dict[str, Any]],
    ) -> BatchObserveResponse:
        data = self._http._request(
            method="POST",
            endpoint="/observations/batch",
            body={"observations": observations},
            is_write=True,
        )
        self._http.flush_buffer()
        return BatchObserveResponse(**data)

    def retrieve(
        self,
        *,
        user_id: str,
        query_text: str,
        session_id: str | None = None,
        memory_types: list[str] | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
        graph_depth: int = 1,
        include_archived: bool = False,
        include_cold: bool = False,
        rerank: bool = False,
    ) -> list[ScoredMemory]:
        body: dict[str, Any] = {
            "query_text": query_text,
            "limit": limit,
            "graph_depth": graph_depth,
            "include_archived": include_archived,
            "include_cold": include_cold,
            "rerank": rerank,
        }
        if session_id:
            body["session_id"] = session_id
        if memory_types:
            body["memory_types"] = memory_types
        if tags:
            body["tags"] = tags
        headers = {"X-contexta-User-Id": user_id}
        data = self._http._request(
            method="POST",
            endpoint="/retrieve",
            body=body,
            headers=headers,
        )
        return [ScoredMemory(**m) for m in data.get("results", [])]

    def retrieve_batch(self, queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Concurrently execute multiple memory retrieval queries in parallel."""
        data = self._http._request(
            method="POST",
            endpoint="/retrieve/batch",
            body={"queries": queries},
        )
        return data.get("batch_results", [])

    def investigate(
        self,
        query: str,
        *,
        user_id: str,
        organization_id: str | None = None,
        max_hops: int = 2,
        limit: int = 15,
    ) -> dict[str, Any]:
        """Execute iterative agentic memory investigation (ASMR-style multi-hop reasoning)."""
        body: dict[str, Any] = {
            "query_text": query,
            "user_id": user_id,
            "max_hops": max_hops,
            "limit": limit,
        }
        if organization_id:
            body["organization_id"] = organization_id
        return self._http._request(
            method="POST",
            endpoint="/retrieve/investigate",
            body=body,
        )

    def search(
        self,
        query: str,
        *,
        user_id: str | None = None,
        limit: int = 20,
        threshold: float = 0.65,
        memory_type: str | None = None,
    ) -> dict[str, Any]:
        """Execute pure vector similarity search over pgvector embeddings."""
        params: dict[str, Any] = {"query": query, "limit": limit, "threshold": threshold}
        if user_id:
            params["user_id"] = user_id
        if memory_type:
            params["memory_type"] = memory_type
        headers = {"X-contexta-User-Id": user_id} if user_id else None
        return self._http._request(
            method="GET",
            endpoint="/memories/search",
            params=params,
            headers=headers,
        )

    def traverse(
        self,
        source: str,
        *,
        hops: int = 2,
        relationship_types: str | None = None,
        direction: str = "both",
    ) -> dict[str, Any]:
        """Execute multi-hop entity graph traversal starting from a root entity name or UUID."""
        params: dict[str, Any] = {"source": source, "hops": hops, "direction": direction}
        if relationship_types:
            params["relationship_types"] = relationship_types
        return self._http._request(
            method="GET",
            endpoint="/graph/traverse",
            params=params,
        )

    def hybrid(
        self,
        query: str,
        *,
        user_id: str | None = None,
        limit: int = 20,
        max_hops: int = 2,
        vector_weight: float = 0.40,
        graph_weight: float = 0.25,
        include_cold: bool = False,
    ) -> dict[str, Any]:
        """Execute multi-signal hybrid retrieval combining vector, graph, recency, and importance."""
        params: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "max_hops": max_hops,
            "vector_weight": vector_weight,
            "graph_weight": graph_weight,
            "include_cold": str(include_cold).lower(),
        }
        if user_id:
            params["user_id"] = user_id
        headers = {"X-contexta-User-Id": user_id} if user_id else None
        return self._http._request(
            method="GET",
            endpoint="/memories/hybrid",
            params=params,
            headers=headers,
        )

    def context(
        self,
        *,
        user_id: str,
        session_id: str,
        organization_id: str | None = None,
        token_budget: int | None = 2000,
        include_user_model: bool = True,
        num_recent_messages: int = 10,
        num_relevant_memories: int = 20,
        graph_depth: int = 2,
    ) -> Context:
        """Assemble token-budgeted memory context for an agent session.

        Hits ``GET /v1/memories/context``, which requires ``user_id``,
        ``organization_id`` and ``session_id``. The server returns 403 when
        ``organization_id`` disagrees with the tenant bound to the API key.
        """
        org_id = self._require_organization_id(organization_id)
        params: dict[str, Any] = {
            "user_id": str(UUID(str(user_id))),
            "organization_id": org_id,
            "session_id": str(UUID(str(session_id))),
            "include_user_model": str(include_user_model).lower(),
            "num_recent_messages": num_recent_messages,
            "num_relevant_memories": num_relevant_memories,
            "graph_depth": graph_depth,
        }
        if token_budget is not None:
            params["token_budget"] = token_budget
        data = self._http._request(
            method="GET",
            endpoint="/memories/context",
            params=params,
            headers={"X-contexta-User-Id": user_id},
        )
        return Context(**data)

    def explain(self, memory_id: str) -> Explanation:
        data = self._http._request(
            method="GET",
            endpoint=f"/memories/{memory_id}/explain",
        )
        return Explanation(**data)

    def get_memory(self, memory_id: str) -> Memory:
        data = self._http._request(
            method="GET",
            endpoint=f"/memories/{memory_id}",
        )
        return Memory(**data)

    def list_memories(
        self,
        *,
        user_id: str | None = None,
        memory_type: str | None = None,
        state: str | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[MemoryListEntry]:
        """List memories for the tenant with optional filters."""
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if user_id:
            params["user_id"] = user_id
        if memory_type:
            params["memory_type"] = memory_type
        if state:
            params["state"] = state
        if pinned is not None:
            params["pinned"] = str(pinned).lower()
        if archived is not None:
            params["archived"] = str(archived).lower()
        data = self._http._request(
            method="GET",
            endpoint="/memories",
            params=params,
            headers={"X-contexta-User-Id": user_id} if user_id else None,
        )
        items = data if isinstance(data, list) else data.get("memories", [])
        return [MemoryListEntry(**item) for item in items]

    def pin(self, memory_id: str) -> MemoryFlag:
        data = self._http._request(
            method="POST",
            endpoint=f"/memories/{memory_id}/pin",
            is_write=True,
        )
        return MemoryFlag(**data)

    def unpin(self, memory_id: str) -> MemoryFlag:
        data = self._http._request(
            method="POST",
            endpoint=f"/memories/{memory_id}/unpin",
            is_write=True,
        )
        return MemoryFlag(**data)

    def archive(self, memory_id: str) -> MemoryFlag:
        data = self._http._request(
            method="POST",
            endpoint=f"/memories/{memory_id}/archive",
            is_write=True,
        )
        return MemoryFlag(**data)

    def restore(self, memory_id: str) -> MemoryFlag:
        data = self._http._request(
            method="POST",
            endpoint=f"/memories/{memory_id}/restore",
            is_write=True,
        )
        return MemoryFlag(**data)

    def delete(self, memory_id: str) -> DeleteResult:
        data = self._http._request(
            method="DELETE",
            endpoint=f"/memories/{memory_id}",
            is_write=True,
        )
        return DeleteResult(**data) if data else DeleteResult(memory_id=memory_id)

    def timeline(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[TimelineEvent]:
        data = self._http._request(
            method="GET",
            endpoint=f"/memories/timeline/{user_id}",
            params={"limit": limit},
        )
        return [TimelineEvent(**e) for e in data.get("events", data if isinstance(data, list) else [])]

    def list_policies(self) -> list[Policy]:
        data = self._http._request(method="GET", endpoint="/policies")
        items = data if isinstance(data, list) else data.get("policies", data.get("data", []))
        return [Policy(**p) for p in items]

    def register_policy(
        self,
        name: str,
        store_rules: list[dict[str, Any]] | None = None,
        ignore_rules: list[dict[str, Any]] | None = None,
        priority_weights: dict[str, float] | None = None,
    ) -> Policy:
        body: dict[str, Any] = {"name": name}
        if store_rules:
            body["store_rules"] = store_rules
        if ignore_rules:
            body["ignore_rules"] = ignore_rules
        if priority_weights:
            body["priority_weights"] = priority_weights
        data = self._http._request(method="POST", endpoint="/policies", body=body, is_write=True)
        return Policy(**data)

    def register_schema(
        self,
        name: str,
        fields: list[dict[str, Any]],
    ) -> Schema:
        body = {
            "name": name,
            "field_definitions": fields,
        }
        data = self._http._request(method="POST", endpoint="/schemas", body=body, is_write=True)
        return Schema(**data)

    def ping(self) -> dict[str, Any]:
        """Check service liveness. Health lives at the root, not under ``/v1``."""
        return self._http._request(method="GET", endpoint="/healthz", absolute=True)

    def create_session(
        self,
        user_id: str,
        organization_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        org_id = self._require_organization_id(organization_id)
        body: dict[str, Any] = {"user_id": user_id, "organization_id": org_id}
        if metadata:
            body["metadata"] = metadata
        data = self._http._request(method="POST", endpoint="/sessions", body=body, is_write=True)
        return Session(**data)

    def get_session(self, session_id: str) -> Session:
        data = self._http._request(
            method="GET",
            endpoint=f"/sessions/{session_id}",
        )
        return Session(**data)

    def end_session(self, session_id: str) -> Session:
        data = self._http._request(
            method="POST",
            endpoint=f"/sessions/{session_id}/end",
            is_write=True,
        )
        return Session(**data)

    def get_many(self, memory_ids: list[str]) -> list[dict[str, Any]]:
        """Concurrently retrieve multiple memory records by ID in a single query."""
        data = self._http._request(
            method="POST",
            endpoint="/memories/batch-get",
            body={"memory_ids": memory_ids},
        )
        return data.get("memories", [])

    def feedback(
        self,
        memory_id: str,
        signal: str,
        user_correction: str | None = None,
        penalty: float = 0.5,
    ) -> FeedbackResult:
        """Submit positive or negative feedback for a memory to adjust utility and contradiction scoring."""
        body: dict[str, Any] = {"signal": signal, "penalty": penalty}
        if user_correction:
            body["user_correction"] = user_correction
        data = self._http._request(
            method="POST",
            endpoint=f"/memories/{memory_id}/feedback",
            body=body,
            is_write=True,
        )
        return FeedbackResult(**data)

    def add_rule(
        self,
        *,
        user_id: str,
        rule: str,
        title: str | None = None,
        tags: list[str] | None = None,
    ) -> ObserveResponse:
        """Store a decay-exempt behavioral directive / operating rule for the agent."""
        rule_tags = (tags or []) + ["rule", "procedural"]
        return self.observe(
            user_id=user_id,
            messages=[
                {"role": "user", "content": f"Instruction / Operating Rule: {rule}"},
                {"role": "assistant", "content": f"Understood. I will strictly follow this rule: {rule}"},
            ],
            metadata={"memory_type": "procedural", "rule_title": title or "Behavioral Rule", "tags": rule_tags},
        )

    def reflect(
        self,
        *,
        user_id: str,
        apply_supersession: bool = True,
        min_occurrences: int = 3,
    ) -> ReflectResult:
        """Run autonomous memory reflection to resolve contradictions and consolidate recurring patterns."""
        data = self._http._request(
            method="POST",
            endpoint="/memories/reflect",
            body={
                "user_id": user_id,
                "apply_supersession": apply_supersession,
                "min_occurrences_for_pattern": min_occurrences,
            },
            is_write=True,
        )
        return ReflectResult(**data)

    def flush(self) -> int:
        """Force the durable offline buffer to drain. Returns entries replayed."""
        return self._http.flush_buffer()

    def close(self) -> None:
        """Release pooled connections. Safe to call more than once."""
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def __getattr__(name: str) -> Any:
    if name == "contexta":
        warnings.warn(
            "contexta_client.client.contexta is deprecated; use Contexta instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return Contexta
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

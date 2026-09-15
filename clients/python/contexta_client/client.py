from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from uuid import UUID

from contexta_client._context_builder import Context
from contexta_client._http import HTTPClient
from contexta_client._types import (
    BatchObserveResponse,
    Explanation,
    Memory,
    ObserveResponse,
    Policy,
    Schema,
    ScoredMemory,
    Session,
    TimelineEvent,
)


class contexta:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.contexta.dev/v1",
        timeout: float = 30.0,
        max_retries: int = 3,
        telemetry: bool = True,
        enable_buffer: bool = True,
        buffer_path: Optional[str] = None,
    ) -> None:
        self._http = HTTPClient(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            telemetry=telemetry,
            enable_buffer=enable_buffer,
            buffer_path=buffer_path,
        )

    @classmethod
    def from_env(cls) -> contexta:
        api_key = os.environ.get("CONTEXTA_API_KEY")
        if not api_key:
            raise ValueError("CONTEXTA_API_KEY environment variable is required")
        return cls(
            api_key=api_key,
            base_url=os.environ.get("CONTEXTA_API_URL", "https://api.contexta.dev/v1"),
            timeout=float(os.environ.get("CONTEXTA_TIMEOUT_MS", "30000")) / 1000.0,
            max_retries=int(os.environ.get("CONTEXTA_MAX_RETRIES", "3")),
            telemetry=os.environ.get("CONTEXTA_TELEMETRY", "true").lower() != "false",
        )

    def observe(
        self,
        *,
        user_id: str,
        session_id: Optional[str] = None,
        messages: List[Dict[str, str]],
        metadata: Optional[Dict[str, Any]] = None,
        policy: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> ObserveResponse:
        body: Dict[str, Any] = {
            "messages": messages,
        }
        if session_id:
            body["session_id"] = session_id
        if metadata:
            body["metadata"] = metadata
        if policy:
            body["policy"] = policy
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
        observations: List[Dict[str, Any]],
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
        session_id: Optional[str] = None,
        memory_types: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        limit: int = 20,
        graph_depth: int = 1,
        include_archived: bool = False,
        include_cold: bool = False,
        rerank: bool = False,
    ) -> List[ScoredMemory]:
        body: Dict[str, Any] = {
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

    def search(
        self,
        query: str,
        *,
        user_id: Optional[str] = None,
        limit: int = 20,
        threshold: float = 0.65,
        memory_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute pure vector similarity search over pgvector embeddings."""
        params = f"?query={query}&limit={limit}&threshold={threshold}"
        if user_id:
            params += f"&user_id={user_id}"
        if memory_type:
            params += f"&memory_type={memory_type}"
        headers = {"X-contexta-User-Id": user_id} if user_id else None
        return self._http._request(
            method="GET",
            endpoint=f"/memories/search{params}",
            headers=headers,
        )

    def traverse(
        self,
        source: str,
        *,
        hops: int = 2,
        relationship_types: Optional[str] = None,
        direction: str = "both",
    ) -> Dict[str, Any]:
        """Execute multi-hop entity graph traversal starting from a root entity name or UUID."""
        params = f"?source={source}&hops={hops}&direction={direction}"
        if relationship_types:
            params += f"&relationship_types={relationship_types}"
        return self._http._request(
            method="GET",
            endpoint=f"/graph/traverse{params}",
        )

    def hybrid(
        self,
        query: str,
        *,
        user_id: Optional[str] = None,
        limit: int = 20,
        max_hops: int = 2,
        vector_weight: float = 0.40,
        graph_weight: float = 0.25,
        include_cold: bool = False,
    ) -> Dict[str, Any]:
        """Execute multi-signal hybrid retrieval combining vector, graph, recency, and importance."""
        params = (
            f"?query={query}&limit={limit}&max_hops={max_hops}"
            f"&vector_weight={vector_weight}&graph_weight={graph_weight}"
            f"&include_cold={str(include_cold).lower()}"
        )
        if user_id:
            params += f"&user_id={user_id}"
        headers = {"X-contexta-User-Id": user_id} if user_id else None
        return self._http._request(
            method="GET",
            endpoint=f"/memories/hybrid{params}",
            headers=headers,
        )

    def context(
        self,
        *,
        user_id: str,
        session_id: Optional[str] = None,
        query: Optional[str] = None,
        token_budget: int = 2000,
        include_user_model: bool = True,
    ) -> Context:
        params: Dict[str, Any] = {
            "user_id": user_id,
            "token_budget": token_budget,
            "include_user_model": str(include_user_model).lower(),
        }
        if session_id:
            params["session_id"] = session_id
        if query:
            params["query"] = query
        data = self._http._request(
            method="GET",
            endpoint="/context",
            params=params,
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

    def pin(self, memory_id: str) -> Memory:
        data = self._http._request(
            method="POST",
            endpoint=f"/memories/{memory_id}/pin",
            is_write=True,
        )
        return Memory(**data)

    def unpin(self, memory_id: str) -> Memory:
        data = self._http._request(
            method="POST",
            endpoint=f"/memories/{memory_id}/unpin",
            is_write=True,
        )
        return Memory(**data)

    def archive(self, memory_id: str) -> Memory:
        data = self._http._request(
            method="POST",
            endpoint=f"/memories/{memory_id}/archive",
            is_write=True,
        )
        return Memory(**data)

    def restore(self, memory_id: str) -> Memory:
        data = self._http._request(
            method="POST",
            endpoint=f"/memories/{memory_id}/restore",
            is_write=True,
        )
        return Memory(**data)

    def delete(self, memory_id: str) -> None:
        self._http._request(
            method="DELETE",
            endpoint=f"/memories/{memory_id}",
            is_write=True,
        )

    def timeline(
        self,
        user_id: str,
        limit: int = 50,
    ) -> List[TimelineEvent]:
        data = self._http._request(
            method="GET",
            endpoint=f"/memories/timeline/{user_id}",
            params={"limit": limit},
        )
        return [TimelineEvent(**e) for e in data.get("events", data if isinstance(data, list) else [])]

    def list_policies(self) -> List[Policy]:
        data = self._http._request(method="GET", endpoint="/policies")
        items = data if isinstance(data, list) else data.get("policies", data.get("data", []))
        return [Policy(**p) for p in items]

    def register_policy(
        self,
        name: str,
        store_rules: Optional[List[Dict[str, Any]]] = None,
        ignore_rules: Optional[List[Dict[str, Any]]] = None,
        priority_weights: Optional[Dict[str, float]] = None,
    ) -> Policy:
        body: Dict[str, Any] = {"name": name}
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
        fields: List[Dict[str, Any]],
    ) -> Schema:
        body = {
            "name": name,
            "field_definitions": fields,
        }
        data = self._http._request(method="POST", endpoint="/schemas", body=body, is_write=True)
        return Schema(**data)

    def ping(self) -> Dict[str, Any]:
        return self._http._request(method="GET", endpoint="/healthz")

    def create_session(
        self,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Session:
        body: Dict[str, Any] = {"user_id": user_id}
        if metadata:
            body["metadata"] = metadata
        data = self._http._request(method="POST", endpoint="/sessions", body=body, is_write=True)
        return Session(**data)

    def end_session(self, session_id: str) -> Session:
        data = self._http._request(
            method="POST",
            endpoint=f"/sessions/{session_id}/end",
            is_write=True,
        )
        return Session(**data)

    def get_many(self, memory_ids: List[str]) -> List[Dict[str, Any]]:
        """Concurrently retrieve multiple memory records by ID in a single query."""
        data = self._http._request(
            method="POST",
            endpoint="/memories/batch-get",
            body={"memory_ids": memory_ids},
        )
        return data.get("memories", [])

    def retrieve_batch(self, queries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Concurrently execute multiple memory retrieval queries in parallel."""
        data = self._http._request(
            method="POST",
            endpoint="/retrieve/batch",
            body={"queries": queries},
        )
        return data.get("batch_results", [])

    def feedback(
        self,
        memory_id: str,
        signal: str,
        user_correction: Optional[str] = None,
        penalty: float = 0.5,
    ) -> Dict[str, Any]:
        """Submit positive or negative feedback for a memory to adjust utility and contradiction scoring."""
        body: Dict[str, Any] = {"signal": signal, "penalty": penalty}
        if user_correction:
            body["user_correction"] = user_correction
        return self._http._request(
            method="POST",
            endpoint=f"/memories/{memory_id}/feedback",
            body=body,
            is_write=True,
        )

    def add_rule(
        self,
        *,
        user_id: str,
        rule: str,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
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

    def investigate(
        self,
        query: str,
        *,
        user_id: str,
        organization_id: Optional[str] = None,
        max_hops: int = 2,
        limit: int = 15,
    ) -> Dict[str, Any]:
        """Execute iterative agentic memory investigation (ASMR-style multi-hop reasoning)."""
        body: Dict[str, Any] = {
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

    def reflect(
        self,
        *,
        user_id: str,
        apply_supersession: bool = True,
        min_occurrences: int = 3,
    ) -> Dict[str, Any]:
        """Run autonomous memory reflection to resolve contradictions and consolidate recurring patterns."""
        return self._http._request(
            method="POST",
            endpoint="/memories/reflect",
            body={
                "user_id": user_id,
                "apply_supersession": apply_supersession,
                "min_occurrences_for_pattern": min_occurrences,
            },
            is_write=True,
        )

    def close(self) -> None:
        self._http.close()



Contexta = contexta


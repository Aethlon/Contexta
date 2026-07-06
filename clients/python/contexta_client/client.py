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

    def close(self) -> None:
        self._http.close()

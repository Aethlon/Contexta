"""Redis response cache and request coalescing for read endpoints.

This is the Python port of the cache that previously lived in the Go gateway. The
gateway is being retired as a second entry point, so the win it provided has to
live here or be lost.

Two behaviours:

* **Response cache** - a repeated read inside a short TTL is served from Redis and
  never reaches the retrieval stack. Recall traffic is highly repetitive: agents
  re-ask the same question while iterating, and the dashboard re-polls.
* **Single-flight** - concurrent identical reads collapse into one upstream call, so
  a burst of N identical asks costs one embedding plus one rerank instead of N.

Safety properties, both covered by tests:

* The cache key includes the resolved tenant, user, API key and the full body, so a
  cached response can never cross a tenant or actor boundary.
* Only an allowlist of read paths is cached. Writes are never cached, and the
  middleware refuses to cache a non-2xx response.

Every Redis interaction here is deliberately fail-open: a cache problem must
degrade to an uncached response, never to a failed request.
"""

# ruff: noqa: BLE001 - the broad excepts below are intentional fail-open guards
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Read endpoints worth caching. TTL in seconds.
CACHEABLE_PATHS: dict[str, float] = {
    "/v1/retrieve": 30.0,
    "/v1/retrieve/batch": 30.0,
    "/v1/retrieve/investigate": 30.0,
    "/v1/memories/context": 30.0,
    "/v1/memories/search": 30.0,
    "/v1/entities/search": 30.0,
    "/v1/graph/search": 30.0,
}
METH_CACHEABLE = {"POST", "GET"}
MAX_CACHEABLE_BODY_BYTES = 1 << 20


class ResponseCacheMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, cacheable_paths: dict[str, float] | None = None) -> None:
        super().__init__(app)
        self._paths = cacheable_paths if cacheable_paths is not None else CACHEABLE_PATHS
        self._redis = None
        self._disabled = False
        self._inflight: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    # -- infrastructure --------------------------------------------------- #

    def _client(self):
        if self._disabled:
            return None
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                from contexta.config.settings import get_settings

                self._redis = aioredis.from_url(get_settings().redis_url)
            except Exception:
                logger.warning("Response cache disabled: Redis unavailable", exc_info=True)
                self._disabled = True
                return None
        return self._redis

    def _identity(self, request: Request) -> tuple[str, str, str]:
        state = request.state
        tenant = str(getattr(state, "organization_id", "") or "")
        user = str(getattr(state, "actor_id", "") or "")
        key_id = str(getattr(state, "api_key_id", "") or "")
        return tenant, user, key_id

    def _cache_key(self, request: Request, body: bytes) -> str:
        tenant, user, key_id = self._identity(request)
        digest = hashlib.sha256()
        for part in (
            request.method,
            request.url.path,
            request.url.query,
            tenant,
            user,
            key_id,
        ):
            digest.update(part.encode("utf-8"))
            digest.update(b"\x00")
        digest.update(body)
        return f"rq:{digest.hexdigest()[:32]}"

    # -- middleware ------------------------------------------------------- #

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        ttl = self._paths.get(request.url.path)
        if ttl is None or request.method not in METH_CACHEABLE:
            return await call_next(request)

        body = b""
        if request.method == "POST":
            try:
                body = await request.body()
                if len(body) > MAX_CACHEABLE_BODY_BYTES:
                    return await call_next(request)
            except Exception:
                return await call_next(request)

        client = self._client()
        if client is None:
            return await call_next(request)

        key = self._cache_key(request, body)

        cached = await self._load(client, key)
        if cached is not None:
            response = _rebuild(cached)
            response.headers["X-Contexta-Cache"] = "hit"
            return response

        # Single-flight: exactly one caller runs the request; identical concurrent
        # callers await the same task. The task, not a bare result, is what gets
        # stored, so waiters and the leader observe identical bytes.
        async with self._lock:
            task = self._inflight.get(key)
            leader = task is None
            if leader:
                task = asyncio.create_task(self._execute(request, call_next, client, key, ttl))
                self._inflight[key] = task

        assert task is not None
        if leader:
            try:
                response = await task
            finally:
                async with self._lock:
                    self._inflight.pop(key, None)
            response.headers["X-Contexta-Cache"] = "miss"
            return response

        try:
            response = await asyncio.shield(task)
        except Exception:
            return await call_next(request)
        response.headers["X-Contexta-Cache"] = "coalesced"
        return response

    async def _execute(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
        client,
        key: str,
        ttl: float,
    ) -> Response:
        response = await call_next(request)
        if not 200 <= response.status_code < 300:
            return response

        # BaseHTTPMiddleware hands back a streaming response whose `.body` is never
        # populated, so the payload has to be drained from `body_iterator` before it
        # can be inspected, cached, or replayed.
        body = await _drain(response)
        if not body:
            return response

        # Skip compression headers: a rebuilt Response computes its own length, and
        # the cached bytes are whatever the inner stack produced.
        headers = {
            name: value
            for name, value in response.headers.items()
            if name.lower() not in {"content-length", "content-encoding"}
        }
        rebuilt = Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
        )

        entry = {
            "status": rebuilt.status_code,
            "headers": {
                name: value
                for name, value in headers.items()
                if name.lower() in {"content-type"}
            },
            "body": body.hex(),
        }
        try:
            await client.set(key, json.dumps(entry), ex=int(ttl))
        except Exception:
            logger.debug("Response cache write failed for %s", key, exc_info=True)
        return rebuilt

    async def _load(self, client, key: str) -> dict | None:
        try:
            raw = await client.get(key)
        except Exception:
            logger.debug("Response cache read failed for %s", key, exc_info=True)
            return None
        if not raw:
            return None
        try:
            entry = json.loads(raw)
            entry["body"] = bytes.fromhex(entry["body"])
        except Exception:
            # A poisoned or stale-format entry is discarded, never served.
            return None
        return entry


def _rebuild(entry: dict) -> Response:
    return Response(
        content=entry["body"],
        status_code=entry["status"],
        headers=entry.get("headers") or {},
        media_type=None,
    )


async def _drain(response: Response) -> bytes:
    """Read a possibly-streaming response body into a single bytes object."""
    if getattr(response, "body", None):
        return bytes(response.body)
    iterator = getattr(response, "body_iterator", None)
    if iterator is None:
        return b""
    chunks: list[bytes] = []
    try:
        async for chunk in iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode())
    except Exception:
        logger.debug("Could not drain response body for caching", exc_info=True)
        return b""
    return b"".join(chunks)

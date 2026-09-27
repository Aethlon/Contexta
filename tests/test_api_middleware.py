"""Tests for the response cache and rate limit middleware.

These guard the two properties that matter most: a cached response must never cross
a tenant boundary, and neither middleware may turn a Redis problem into a failed
request.
"""

from __future__ import annotations

import asyncio

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from contexta.api.middleware import ratelimit
from contexta.api.middleware.ratelimit import RateLimitMiddleware
from contexta.api.middleware.response_cache import ResponseCacheMiddleware


class FakeRedis:
    """Minimal in-memory stand-in with failure injection."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.fail = False

    async def get(self, key: str):
        if self.fail:
            raise RuntimeError("redis down")
        value = self.store.get(key)
        return value

    async def set(self, key: str, value: str, ex: int | None = None):
        if self.fail:
            raise RuntimeError("redis down")
        self.store[key] = value
        return True

    async def delete(self, key: str):
        self.store.pop(key, None)

    def pipeline(self, transaction: bool = True):
        # redis-py returns a Pipeline object from a *sync* method, which is then
        # used as an async context manager.
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.ops: list[tuple] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def get(self, key):
        self.ops.append(("get", key))
        return self

    def set(self, key, value):
        self.ops.append(("set", key, value))
        return self

    def expire(self, key, ttl):
        self.ops.append(("expire", key))
        return self

    async def execute(self):
        if self.redis.fail:
            raise RuntimeError("redis down")
        results = []
        for op in self.ops:
            if op[0] == "get":
                results.append(self.redis.store.get(op[1]))
            else:
                if op[0] == "set":
                    self.redis.store[op[1]] = op[2]
                results.append(True)
        return results


def build_app(middleware_factory, calls: list[int]):
    async def retrieve(request):
        calls[0] += 1
        return JSONResponse({"hits": [1, 2, 3], "n": calls[0]})

    async def observe(request):
        calls[0] += 1
        return JSONResponse({"job_id": f"job-{calls[0]}"})

    app = Starlette(
        routes=[
            Route("/v1/retrieve", retrieve, methods=["GET", "POST"]),
            Route("/v1/observations", observe, methods=["POST"]),
        ]
    )
    app.add_middleware(middleware_factory)
    return app


def make_cache(fake: FakeRedis):
    class _Cache(ResponseCacheMiddleware):
        def _client(self):
            return fake

    return _Cache


def make_limiter(fake: FakeRedis):
    class _Limiter(RateLimitMiddleware):
        def _client(self):
            return fake

    return _Limiter


# --------------------------------------------------------------------------- #
# Response cache
# --------------------------------------------------------------------------- #


def test_repeat_read_is_served_from_cache():
    fake = FakeRedis()
    calls = [0]
    app = build_app(make_cache(fake), calls)
    with TestClient(app) as client:
        first = client.post("/v1/retrieve", json={"q": "hello"})
        second = client.post("/v1/retrieve", json={"q": "hello"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers.get("X-Contexta-Cache") == "hit"
    assert calls[0] == 1, "second identical read must not reach the route"
    assert first.json() == second.json()


def test_different_body_is_a_separate_entry():
    fake = FakeRedis()
    calls = [0]
    app = build_app(make_cache(fake), calls)
    with TestClient(app) as client:
        client.post("/v1/retrieve", json={"q": "a"})
        client.post("/v1/retrieve", json={"q": "b"})
    assert calls[0] == 2


def test_writes_are_never_cached():
    fake = FakeRedis()
    calls = [0]
    app = build_app(make_cache(fake), calls)
    with TestClient(app) as client:
        client.post("/v1/observations", json={})
        client.post("/v1/observations", json={})
    assert calls[0] == 2
    assert fake.store == {}


def test_cache_degrades_when_redis_fails():
    fake = FakeRedis()
    fake.fail = True
    calls = [0]
    app = build_app(make_cache(fake), calls)
    with TestClient(app) as client:
        first = client.post("/v1/retrieve", json={"q": "x"})
        second = client.post("/v1/retrieve", json={"q": "x"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert calls[0] == 2, "a Redis outage must not be served from cache"


def test_concurrent_identical_reads_are_coalesced():
    fake = FakeRedis()
    calls = [0]

    async def slow(request):
        calls[0] += 1
        await asyncio.sleep(0.05)
        return JSONResponse({"n": calls[0]})

    app = Starlette(routes=[Route("/v1/retrieve", slow, methods=["POST"])])
    app.add_middleware(make_cache(fake))

    with TestClient(app) as client:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(client.post, "/v1/retrieve", json={"q": "burst"})
                for _ in range(8)
            ]
            responses = [f.result() for f in futures]

    assert calls[0] == 1, f"expected 1 upstream call, got {calls[0]}"
    assert all(r.status_code == 200 for r in responses)
    bodies = {r.json()["n"] for r in responses}
    assert len(bodies) == 1, "coalesced callers must see identical payloads"


def test_health_endpoints_are_not_cached():
    fake = FakeRedis()
    calls = [0]

    async def healthz(request):
        calls[0] += 1
        return JSONResponse({"status": "ok", "n": calls[0]})

    app = Starlette(routes=[Route("/healthz", healthz, methods=["GET"])])
    app.add_middleware(make_cache(fake))
    with TestClient(app) as client:
        a = client.get("/healthz")
        b = client.get("/healthz")
    assert a.json()["n"] != b.json()["n"]
    assert calls[0] == 2


def test_tenant_isolation_in_cache_key():
    """Two tenants sending the same body must not share a cached response."""
    fake = FakeRedis()
    seen: list[str | None] = []

    async def retrieve(request):
        seen.append(request.state.organization_id)
        return JSONResponse({"tenant": request.state.organization_id})

    app = Starlette(routes=[Route("/v1/retrieve", retrieve, methods=["POST"])])

    class FakeAuthMiddleware:
        """Stands in for AuthenticationMiddleware, which populates request.state."""

        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return
            headers = dict(scope["headers"])
            state = scope.setdefault("state", {})
            for raw, name in ((b"x-organization-id", "organization_id"),
                              (b"x-user-id", "actor_id"),
                              (b"x-api-key", "api_key_id")):
                value = headers.get(raw)
                state[name] = value.decode() if value else None
            await self.app(scope, receive, send)

    # Auth must run *outside* the cache, exactly as in contexta/api/app.py.
    app.add_middleware(make_cache(fake))
    app.add_middleware(FakeAuthMiddleware)

    with TestClient(app) as client:
        a = client.post("/v1/retrieve", json={"q": "same"},
                        headers={"x-organization-id": "org-a", "x-user-id": "u1",
                                 "x-api-key": "k1"})
        b = client.post("/v1/retrieve", json={"q": "same"},
                        headers={"x-organization-id": "org-b", "x-user-id": "u2",
                                 "x-api-key": "k2"})

    assert a.json()["tenant"] == "org-a"
    assert b.json()["tenant"] == "org-b", "org-b received org-a's cached body"
    assert b.headers.get("X-Contexta-Cache") != "hit"
    assert seen == ["org-a", "org-b"]


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #


def test_rate_limit_blocks_after_burst_is_exhausted(monkeypatch):
    fake = FakeRedis()
    # The api_key table has no tier column, so every key uses the default tier.
    # Shrink it here so the limit is reached deterministically.
    monkeypatch.setitem(
        ratelimit.TIER_LIMITS, ratelimit.DEFAULT_TIER, (1.0, 3)
    )
    app = build_app(make_limiter(fake), [0])
    with TestClient(app) as client:
        # Distinct bodies so the response cache cannot mask the limiter.
        codes = [client.post("/v1/retrieve", json={"q": str(i)}).status_code
                 for i in range(8)]
    assert codes[0] == 200, "the first request must be allowed"
    assert 429 in codes, f"expected the limiter to engage, got {codes}"


def test_rate_limit_is_per_identity(monkeypatch):
    """One noisy caller must not throttle a different API key."""
    fake = FakeRedis()
    monkeypatch.setitem(ratelimit.TIER_LIMITS, ratelimit.DEFAULT_TIER, (1.0, 2))

    async def retrieve(request):
        return JSONResponse({"n": 1})

    app = Starlette(routes=[Route("/v1/retrieve", retrieve, methods=["POST"])])

    class FakeAuth:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                headers = dict(scope["headers"])
                key = headers.get(b"x-api-key")
                scope.setdefault("state", {})["api_key_id"] = (
                    key.decode() if key else None
                )
            await self.app(scope, receive, send)

    app.add_middleware(make_limiter(fake))
    app.add_middleware(FakeAuth)

    with TestClient(app) as client:
        noisy = [client.post("/v1/retrieve", json={"q": str(i)},
                             headers={"x-api-key": "noisy"}).status_code
                 for i in range(6)]
        other = client.post("/v1/retrieve", json={"q": "x"},
                            headers={"x-api-key": "quiet"}).status_code

    assert 429 in noisy
    assert other == 200, "a different API key must not inherit the noisy key's limit"


def test_rate_limit_never_blocks_health_checks():
    fake = FakeRedis()
    calls = [0]

    async def healthz(request):
        calls[0] += 1
        return JSONResponse({"status": "ok"})

    app = Starlette(routes=[Route("/healthz", healthz, methods=["GET"])])
    app.add_middleware(make_limiter(fake))
    with TestClient(app) as client:
        for _ in range(50):
            assert client.get("/healthz").status_code == 200


def test_rate_limit_fails_open_when_redis_is_down():
    fake = FakeRedis()
    fake.fail = True
    app = build_app(make_limiter(fake), [0])
    with TestClient(app) as client:
        for _ in range(30):
            assert client.post("/v1/retrieve", json={"q": "x"}).status_code == 200


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

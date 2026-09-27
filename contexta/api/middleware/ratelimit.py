"""Redis-backed rate limiting for the public API.

This replaces the Go gateway's limiter. The gateway is being retired as a second
entry point, so the limits it enforced (per API key, per tier) move here where the
API key is actually resolved from Postgres.

The limiter is fail-open: if Redis is unavailable the request is allowed through.
Failing closed would turn a cache outage into a total outage, and the API already
has tenant isolation and authentication as the real controls.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Requests per second and burst allowance, per API key tier.
TIER_LIMITS: dict[str, tuple[float, int]] = {
    "hobby": (10.0, 20),
    "solo_pro": (50.0, 100),
    "team": (250.0, 500),
    "scale": (1000.0, 2000),
    "standard": (50.0, 100),
}
DEFAULT_TIER = "standard"

# Paths that are not metered: health checks must never be throttled, and reads that
# are served from the response cache should not consume a caller's budget twice.
UNMETERED_PREFIXES = ("/healthz", "/readyz", "/metrics", "/docs", "/openapi.json", "/redoc")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket rate limiting keyed by API key, with a per-IP fallback."""

    def __init__(self, app, *, unmetered_prefixes: tuple[str, ...] = UNMETERED_PREFIXES) -> None:
        super().__init__(app)
        self._unmetered = unmetered_prefixes
        self._redis = None
        self._disabled = False

    def _client(self):
        if self._disabled:
            return None
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                from contexta.config.settings import get_settings

                self._redis = aioredis.from_url(
                    get_settings().redis_url, decode_responses=True
                )
            except Exception:
                logger.warning("Rate limiting disabled: Redis unavailable", exc_info=True)
                self._disabled = True
                return None
        return self._redis

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if any(path.startswith(prefix) for prefix in self._unmetered):
            return await call_next(request)

        key_id = getattr(request.state, "api_key_id", None)
        if key_id:
            tier = str(getattr(request.state, "api_key_tier", "") or DEFAULT_TIER)
            identity = f"apikey:{key_id}"
        else:
            client = request.client
            tier = DEFAULT_TIER
            identity = f"ip:{client.host if client else 'unknown'}"

        rate, burst = TIER_LIMITS.get(tier, TIER_LIMITS[DEFAULT_TIER])
        allowed, retry_after = await self._consume(identity, rate, burst)
        if allowed:
            return await call_next(request)

        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limited",
                "message": f"Rate limit exceeded for tier '{tier}'.",
                "retry_after": round(retry_after, 3),
            },
            headers={"Retry-After": str(max(1, int(retry_after) + 1))},
        )

    async def _consume(self, identity: str, rate: float, burst: int) -> tuple[bool, float]:
        """Take one token. Returns (allowed, seconds_until_available)."""
        client = self._client()
        if client is None:
            return True, 0.0

        now = time.time()
        tokens_key = f"rl:{identity}:tokens"
        ts_key = f"rl:{identity}:ts"
        try:
            async with client.pipeline(transaction=True) as pipe:
                pipe.get(ts_key)
                pipe.get(tokens_key)
                previous_ts, previous_tokens = await pipe.execute()

                if previous_ts is None:
                    available = float(burst)
                else:
                    elapsed = max(0.0, now - float(previous_ts))
                    available = min(float(burst), float(previous_tokens or burst) + elapsed * rate)

                if available >= 1.0:
                    remaining = available - 1.0
                    allowed = True
                    retry_after = 0.0
                else:
                    remaining = available
                    allowed = False
                    retry_after = (1.0 - available) / rate if rate > 0 else 1.0

                pipe.set(tokens_key, remaining)
                pipe.expire(tokens_key, 120)
                pipe.set(ts_key, now)
                pipe.expire(ts_key, 120)
                await pipe.execute()
            return allowed, retry_after
        except Exception:
            logger.debug("Rate limit check failed; allowing request", exc_info=True)
            return True, 0.0
